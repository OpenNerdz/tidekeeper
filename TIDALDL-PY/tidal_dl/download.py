#!/usr/bin/env python
# -*- encoding: utf-8 -*-
'''
@File    :   download.py
@Time    :   2020/11/08
@Author  :   Yaronzz
@Version :   1.0
@Contact :   yaronhuang@foxmail.com
@Desc    :
'''

import logging
import os
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, local

import aigpy
import requests

from .decryption import *
from .printf import *
from .tidal import *


DOWNLOAD_TIMEOUT = (5, 60)
DEFAULT_PART_SIZE = 1048576
TRACK_THREAD_COUNT = 5
VIDEO_THREAD_COUNT = 8
DOWNLOAD_RETRIES = 4
DOWNLOAD_CHUNK_SIZE = 256 * 1024
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
FAILED_TRACKS_FILE = "failed-tracks.txt"
failed_track_log_lock = Lock()
download_session_state = local()


def __httpSession__():
    session = getattr(download_session_state, "session", None)
    if session is None:
        session = requests.Session()
        pool_size = max(TRACK_THREAD_COUNT, VIDEO_THREAD_COUNT) + 2
        adapter = requests.adapters.HTTPAdapter(pool_connections=pool_size, pool_maxsize=pool_size)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        download_session_state.session = session
    return session


def __removeFile__(path):
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError as e:
        logging.warning("Unable to remove temporary file %s: %s", path, e)


def __removeDir__(path):
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
    except OSError as e:
        logging.warning("Unable to remove temporary directory %s: %s", path, e)


def __failedTrackLogPath__():
    return os.path.join(SETTINGS.downloadPath or ".", FAILED_TRACKS_FILE)


def __tidalTrackUrl__(track):
    return f"https://tidal.com/browse/track/{getattr(track, 'id', '')}"


def __oneLine__(value):
    return " ".join(str(value).split())


def __logFailedTrack__(track, album=None, playlist=None, reason=""):
    track_id = getattr(track, 'id', None)
    if track_id is None:
        return

    try:
        path = __failedTrackLogPath__()
        __ensureParentDir__(path)
        context = []
        album_title = getattr(album, 'title', None)
        playlist_title = getattr(playlist, 'title', None)
        if album_title:
            context.append(f"album={__oneLine__(album_title)}")
        if playlist_title:
            context.append(f"playlist={__oneLine__(playlist_title)}")

        title = getattr(track, 'title', None) or str(track_id)
        parts = [
            time.strftime("%Y-%m-%d %H:%M:%S"),
            f"track={__oneLine__(title)}",
            f"id={track_id}",
        ]
        parts.extend(context)
        if reason:
            parts.append(f"reason={__oneLine__(reason)}")
        entry = "# " + " | ".join(parts) + "\n" + __tidalTrackUrl__(track) + "\n"

        with failed_track_log_lock:
            with open(path, "a", encoding="utf-8") as output:
                output.write(entry)
    except Exception as e:
        logging.warning("Unable to log failed track %s: %s", track_id, e)


def __ensureParentDir__(path):
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def __retryDelay__(response, attempt):
    if response is not None and response.headers.get("Retry-After"):
        try:
            return min(float(response.headers["Retry-After"]), 60)
        except ValueError:
            pass
    return min(2 ** attempt, 20)


def __httpRequest__(method, url, **kwargs):
    last_error = None
    for attempt in range(DOWNLOAD_RETRIES):
        response = None
        try:
            response = __httpSession__().request(method, url, timeout=DOWNLOAD_TIMEOUT, **kwargs)
            if response.status_code in RETRYABLE_STATUS_CODES and attempt < DOWNLOAD_RETRIES - 1:
                response.close()
                time.sleep(__retryDelay__(response, attempt))
                continue
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            last_error = e
            if response is not None:
                response.close()
            if attempt < DOWNLOAD_RETRIES - 1:
                time.sleep(__retryDelay__(response, attempt))
                continue
            raise
    raise last_error


def __contentLength__(url):
    try:
        response = __httpRequest__("HEAD", url, allow_redirects=True)
        response.close()
        length = response.headers.get("Content-Length")
        return int(length) if length is not None else -1
    except Exception:
        return -1


def __remoteSize__(urls):
    if isinstance(urls, str):
        urls = [urls]

    total = 0
    for url in urls or []:
        size = __contentLength__(url)
        if size <= 0:
            return -1
        total += size
    return total


def __setUserProgressMax__(userProgress, size):
    if userProgress is None or size <= 0:
        return
    try:
        userProgress.setMaxNum(size)
    except Exception:
        pass


def __addUserProgress__(userProgress, size):
    if userProgress is None or size <= 0:
        return
    try:
        userProgress.addCurNum(size)
    except Exception:
        pass


def __downloadUrlToPath__(url, path, progress=None, userProgress=None, progressLock=None, chunkSize=DOWNLOAD_CHUNK_SIZE):
    tempPath = path + '.part'
    __removeFile__(tempPath)
    response = __httpRequest__("GET", url, stream=True, allow_redirects=True)
    try:
        with open(tempPath, "wb") as output:
            for chunk in response.iter_content(chunk_size=chunkSize):
                if not chunk:
                    continue
                output.write(chunk)
                size = len(chunk)
                if progress is not None:
                    progress.addCurCount(size)
                if progressLock is not None:
                    with progressLock:
                        __addUserProgress__(userProgress, size)
                else:
                    __addUserProgress__(userProgress, size)
        os.replace(tempPath, path)
    finally:
        response.close()
        __removeFile__(tempPath)


def __addExistingProgress__(progress, userProgress, size):
    if size <= 0:
        return
    if progress is not None:
        try:
            progress.addCurCount(size)
        except Exception:
            pass
    __addUserProgress__(userProgress, size)


def __contentRangeStart__(response):
    contentRange = response.headers.get("Content-Range", "")
    if not contentRange.lower().startswith("bytes "):
        return None
    try:
        return int(contentRange.split(" ", 1)[1].split("-", 1)[0])
    except (IndexError, ValueError):
        return None


def __downloadSingleUrl__(url, outputPath, progress=None, userProgress=None, chunkSize=DOWNLOAD_CHUNK_SIZE):
    tempOutputPath = outputPath + ".download"
    resumeSize = aigpy.file.getSize(tempOutputPath)
    headers = {}
    if resumeSize > 0:
        headers["Range"] = f"bytes={resumeSize}-"

    response = __httpRequest__("GET", url, stream=True, allow_redirects=True, headers=headers)
    try:
        mode = "wb"
        if resumeSize > 0 and response.status_code == 206 and __contentRangeStart__(response) == resumeSize:
            mode = "ab"
            __addExistingProgress__(progress, userProgress, resumeSize)
        elif resumeSize > 0:
            __removeFile__(tempOutputPath)
            resumeSize = 0

        with open(tempOutputPath, mode) as output:
            for chunk in response.iter_content(chunk_size=chunkSize):
                if not chunk:
                    continue
                output.write(chunk)
                size = len(chunk)
                if progress is not None:
                    progress.addCurCount(size)
                __addUserProgress__(userProgress, size)

        os.replace(tempOutputPath, outputPath)
    finally:
        response.close()


def __downloadUrls__(
        urls,
        outputPath,
        showProgress=False,
        userProgress=None,
        threadNum=1,
        chunkSize=DOWNLOAD_CHUNK_SIZE,
        probeSize=True):
    urls = [url for url in (urls or []) if not aigpy.string.isNull(url)]
    if len(urls) <= 0:
        return False, "URL list is empty."

    __ensureParentDir__(outputPath)
    tempOutputPath = f"{outputPath}.tmp.{os.getpid()}"
    __removeFile__(tempOutputPath)

    totalSize = __remoteSize__(urls) if probeSize else -1
    progress = None
    if totalSize > 0:
        __setUserProgressMax__(userProgress, totalSize)
        if showProgress:
            progress = aigpy.progress.ProgressTool(totalSize, 15, unit="B")

    if len(urls) == 1 or threadNum <= 1:
        try:
            if len(urls) == 1:
                __downloadSingleUrl__(urls[0], outputPath, progress, userProgress, chunkSize)
                return True, ''

            with open(tempOutputPath, "wb") as output:
                for url in urls:
                    response = __httpRequest__("GET", url, stream=True, allow_redirects=True)
                    try:
                        for chunk in response.iter_content(chunk_size=chunkSize):
                            if not chunk:
                                continue
                            output.write(chunk)
                            size = len(chunk)
                            if progress is not None:
                                progress.addCurCount(size)
                            __addUserProgress__(userProgress, size)
                    finally:
                        response.close()
            os.replace(tempOutputPath, outputPath)
            return True, ''
        except Exception as e:
            __removeFile__(tempOutputPath)
            return False, str(e)

    partsDir = tempOutputPath + '.parts'
    __removeDir__(partsDir)
    os.makedirs(partsDir, exist_ok=True)
    progressLock = Lock()

    try:
        with ThreadPoolExecutor(max_workers=threadNum) as thread_pool:
            futures = []
            for index, url in enumerate(urls):
                partPath = os.path.join(partsDir, f"{index:08d}.part")
                futures.append(thread_pool.submit(
                    __downloadUrlToPath__,
                    url,
                    partPath,
                    progress,
                    userProgress,
                    progressLock,
                    chunkSize,
                ))

            for future in as_completed(futures):
                future.result()

        with open(tempOutputPath, "wb") as output:
            for index in range(len(urls)):
                partPath = os.path.join(partsDir, f"{index:08d}.part")
                with open(partPath, "rb") as inputFile:
                    shutil.copyfileobj(inputFile, output)
        os.replace(tempOutputPath, outputPath)
        return True, ''
    except Exception as e:
        __removeFile__(tempOutputPath)
        return False, str(e)
    finally:
        __removeDir__(partsDir)


def __isSkip__(finalpath, urls):
    if not SETTINGS.checkExist:
        return False
    curSize = aigpy.file.getSize(finalpath)
    if curSize <= 0:
        return False
    netSize = __remoteSize__(urls)
    if netSize <= 0:
        return False
    return curSize >= netSize


def __downloadErrorHint__(err):
    text = str(err or "").lower()
    if any(item in text for item in ("429", "too many requests", "rate limit")):
        return " (hint: raise the request interval in settings and retry)"
    if any(item in text for item in ("403", "entitled", "not allowed", "client_not_entitled")):
        return " (hint: stream may be unavailable for this account or quality; try a lower quality/fallback order)"
    if any(item in text for item in ("timeout", "connection", "network", "name or service not known")):
        return " (hint: check network/VPN/proxy/firewall, or run tidekeeper --doctor)"
    if any(item in text for item in ("permission", "denied", "access is denied", "readonly")):
        return " (hint: choose a writable download folder outside protected system directories)"
    if "disk" in text or "space" in text or "no space" in text:
        return " (hint: check available disk space)"
    return ""


def __encrypted__(stream, srcPath, descPath):
    if aigpy.string.isNull(stream.encryptionKey):
        os.replace(srcPath, descPath)
    else:
        key, nonce = decrypt_security_token(stream.encryptionKey)
        decrypt_file(srcPath, descPath, key, nonce)
        os.remove(srcPath)


def __isFlacInM4a__(stream):
    codec = (getattr(stream, 'codec', None) or '').lower()
    container = (getattr(stream, 'container', None) or '').lower()
    manifestMimeType = (getattr(stream, 'manifestMimeType', None) or '').lower()
    return 'flac' in codec and ('mp4' in container or 'dash+xml' in manifestMimeType)


def __containerFallbackPath__(path):
    return path.rsplit('.', 1)[0] + '.m4a'


def __skipPath__(path, stream):
    if __isSkip__(path, stream.urls):
        return path

    if not SETTINGS.checkExist:
        return None

    if SETTINGS.saveAsFlac and __isFlacInM4a__(stream):
        for candidate in (path, __containerFallbackPath__(path)):
            if aigpy.file.getSize(candidate) > 0:
                return candidate
    return None


def __exportFlacFromContainer__(path, stream):
    if not SETTINGS.saveAsFlac or not __isFlacInM4a__(stream):
        return path

    flacPath = path.rsplit('.', 1)[0] + '.flac'
    fallbackPath = __containerFallbackPath__(path)
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        logging.warning("saveAsFlac is enabled but ffmpeg was not found; saving container as %s", fallbackPath)
        if os.path.abspath(path) != os.path.abspath(fallbackPath):
            os.replace(path, fallbackPath)
        return fallbackPath

    tempPath = f"{flacPath}.tmp.{os.getpid()}.flac"
    __removeFile__(tempPath)
    try:
        completed = subprocess.run(
            [ffmpeg, '-y', '-hide_banner', '-loglevel', 'error', '-i', path, '-map', '0:a:0', '-c', 'copy', '-f', 'flac', tempPath],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or '').strip()
            raise RuntimeError(detail or f"ffmpeg exited with code {completed.returncode}")
        os.replace(tempPath, flacPath)
        if os.path.abspath(path) != os.path.abspath(flacPath):
            __removeFile__(path)
        return flacPath
    except Exception as e:
        __removeFile__(tempPath)
        logging.warning("Unable to export FLAC for %s: %s; saving container as %s", path, e, fallbackPath)
        if os.path.abspath(path) != os.path.abspath(fallbackPath):
            os.replace(path, fallbackPath)
        return fallbackPath


def __lyricsText__(value):
    if value is None:
        return ''
    text = str(value)
    return text if text.strip() else ''


def __hasTimedLyrics__(lyricsData):
    return bool(__lyricsText__(getattr(lyricsData, 'subtitles', None)))


def __lyricsPayload__(lyricsData):
    if lyricsData is None:
        return '', '', ''

    subtitles = __lyricsText__(getattr(lyricsData, 'subtitles', None))
    lyrics = __lyricsText__(getattr(lyricsData, 'lyrics', None))
    metadataLyrics = lyrics or subtitles

    if subtitles:
        return metadataLyrics, subtitles, '.lrc'
    if lyrics:
        return metadataLyrics, lyrics, '.txt'
    return '', '', ''


def __writeTextFile__(path, content):
    __ensureParentDir__(path)
    tempPath = f"{path}.tmp.{os.getpid()}"
    try:
        with open(tempPath, 'w', encoding='utf-8', newline='') as output:
            output.write(content)
        os.replace(tempPath, path)
    except Exception:
        __removeFile__(tempPath)
        raise


def __writeLyricsFile__(trackPath, lyricsData):
    metadataLyrics, fileLyrics, extension = __lyricsPayload__(lyricsData)
    if SETTINGS.lyricFile and fileLyrics:
        lyricPath = trackPath.rsplit(".", 1)[0] + extension
        __writeTextFile__(lyricPath, fileLyrics)
    return metadataLyrics


def __normalizeLyricsMatchText__(value):
    return " ".join(str(value or "").casefold().split())


def __rawArtistNames__(artists):
    return [
        str(getattr(artist, 'name', '')).strip()
        for artist in (artists or [])
        if getattr(artist, 'name', None)
    ]


def __artistNames__(artists):
    return [
        __normalizeLyricsMatchText__(getattr(artist, 'name', ''))
        for artist in (artists or [])
        if getattr(artist, 'name', None)
    ]


def __albumTitle__(item):
    album = getattr(item, 'album', None)
    return __normalizeLyricsMatchText__(getattr(album, 'title', ''))


def __lyricsCandidateScore__(track, candidate):
    if getattr(candidate, 'id', None) == getattr(track, 'id', None):
        return -1

    if __normalizeLyricsMatchText__(getattr(track, 'title', '')) != __normalizeLyricsMatchText__(getattr(candidate, 'title', '')):
        return -1

    trackArtists = set(__artistNames__(getattr(track, 'artists', [])))
    candidateArtists = set(__artistNames__(getattr(candidate, 'artists', [])))
    if not trackArtists or not candidateArtists:
        return -1

    artistOverlap = trackArtists.intersection(candidateArtists)
    if not artistOverlap:
        return -1

    score = 100 + (min(len(artistOverlap), 3) * 20)

    trackArtistOrder = __artistNames__(getattr(track, 'artists', []))
    candidateArtistOrder = __artistNames__(getattr(candidate, 'artists', []))
    if trackArtistOrder and candidateArtistOrder and trackArtistOrder[0] == candidateArtistOrder[0]:
        score += 15

    trackIsrc = str(getattr(track, 'isrc', '') or '').strip()
    candidateIsrc = str(getattr(candidate, 'isrc', '') or '').strip()
    if trackIsrc and candidateIsrc:
        score += 50 if trackIsrc == candidateIsrc else -5

    try:
        durationDelta = abs(int(getattr(track, 'duration', 0) or 0) - int(getattr(candidate, 'duration', 0) or 0))
        if durationDelta <= 2:
            score += 20
        elif durationDelta <= 5:
            score += 10
    except Exception:
        pass

    trackAlbum = __albumTitle__(track)
    candidateAlbum = __albumTitle__(candidate)
    if trackAlbum and candidateAlbum and trackAlbum == candidateAlbum:
        score += 10

    noisyAlbumWords = ('commentary', 'sing-along', 'karaoke', 'instrumental')
    if any(word in candidateAlbum for word in noisyAlbumWords):
        score -= 15

    return score


def __mergeLyrics__(primary, timed):
    if primary is None:
        return timed
    if timed is None or not __hasTimedLyrics__(timed):
        return primary

    merged = Lyrics()
    merged.trackId = getattr(primary, 'trackId', None) or getattr(timed, 'trackId', None)
    merged.lyricsProvider = getattr(primary, 'lyricsProvider', None) or getattr(timed, 'lyricsProvider', None)
    merged.providerCommontrackId = getattr(primary, 'providerCommontrackId', None) or getattr(timed, 'providerCommontrackId', None)
    merged.providerLyricsId = getattr(primary, 'providerLyricsId', None) or getattr(timed, 'providerLyricsId', None)
    merged.lyrics = __lyricsText__(getattr(primary, 'lyrics', None)) or __lyricsText__(getattr(timed, 'lyrics', None))
    merged.subtitles = getattr(timed, 'subtitles', None)
    return merged


def __findTimedLyricsForTrack__(track):
    title = getattr(track, 'title', None)
    if aigpy.string.isNull(title):
        return None

    queries = []
    artists = __rawArtistNames__(getattr(track, 'artists', []))
    for artist in artists[:5]:
        queries.append(f"{title} {artist}")
    if len(artists) > 1:
        queries.append(f"{title} {' '.join(artists[:2])}")
    queries.append(str(title))

    candidatesById = {}
    for query in dict.fromkeys(queries):
        try:
            result = TIDAL_API.search(query, Type.Track, limit=10)
            candidates = TIDAL_API.getSearchResultItems(result, Type.Track)
        except Exception as e:
            logging.info("Unable to search timed lyrics fallback for track %s: %s", getattr(track, 'id', ''), e)
            continue

        for candidate in candidates:
            candidateId = getattr(candidate, 'id', None)
            if candidateId is not None:
                candidatesById[candidateId] = candidate

    scoredCandidates = sorted(
        (
            (score, candidate)
            for candidate in candidatesById.values()
            for score in [__lyricsCandidateScore__(track, candidate)]
            if score >= 0
        ),
        key=lambda item: item[0],
        reverse=True,
    )

    for score, candidate in scoredCandidates:
        try:
            lyrics = TIDAL_API.getLyrics(candidate.id)
        except Exception:
            continue
        if __hasTimedLyrics__(lyrics):
            return lyrics
    return None


def __getLyricsForTrack__(track):
    primary = None
    try:
        primary = TIDAL_API.getLyrics(track.id)
    except Exception as e:
        logging.info("Unable to get lyrics for track %s: %s", getattr(track, 'id', ''), e)

    if not SETTINGS.lyricFile or __hasTimedLyrics__(primary):
        return primary

    return __mergeLyrics__(primary, __findTimedLyricsForTrack__(track))


def __saveLyricsForTrack__(track, trackPath):
    try:
        return __writeLyricsFile__(trackPath, __getLyricsForTrack__(track))
    except Exception as e:
        logging.info("Unable to save lyrics for track %s: %s", getattr(track, 'id', ''), e)
        return ''


def __parseContributors__(roleType, Contributors):
    if Contributors is None:
        return None
    try:
        ret = []
        for item in Contributors['items']:
            if item['role'] == roleType:
                ret.append(item['name'])
        return ret
    except:
        return None


def __metadataSaveError__(result):
    if isinstance(result, tuple):
        if len(result) > 0 and result[0] is False:
            return str(result[1]) if len(result) > 1 else "metadata writer returned false"
        return None
    if result is False:
        return "metadata writer returned false"
    return None


def __ensureMetadataTags__(tagTool):
    handle = getattr(tagTool, '_handle', None)
    if handle is not None and getattr(handle, 'tags', None) is None and hasattr(handle, 'add_tags'):
        handle.add_tags()


def __setMetaData__(track: Track, album: Album, filepath, contributors, lyrics):
    obj = aigpy.tag.TagTool(filepath)
    obj.album = track.album.title
    obj.title = track.title
    if not aigpy.string.isNull(track.version):
        obj.title += ' (' + track.version + ')'

    obj.artist = list(map(lambda artist: artist.name, track.artists))
    obj.copyright = track.copyRight
    obj.tracknumber = track.trackNumber
    obj.discnumber = track.volumeNumber
    obj.composer = __parseContributors__('Composer', contributors)
    obj.isrc = track.isrc

    obj.albumartist = list(map(lambda artist: artist.name, album.artists))
    obj.date = album.releaseDate
    obj.totaldisc = album.numberOfVolumes
    obj.lyrics = lyrics
    if obj.totaldisc <= 1:
        obj.totaltrack = album.numberOfTracks
    coverpath = TIDAL_API.getCoverUrl(album.cover, "1280", "1280")
    __ensureMetadataTags__(obj)
    error = __metadataSaveError__(obj.save(coverpath))
    if error is not None:
        raise Exception(error)


def downloadCover(album):
    if album is None:
        return False, "Album is empty."
    path = getAlbumPath(album) + '/cover.jpg'
    url = TIDAL_API.getCoverUrl(album.cover, "1280", "1280")
    if aigpy.string.isNull(url):
        return False, "Cover URL is empty."

    check, err = __downloadUrls__([url], path, SETTINGS.showProgress, threadNum=1)
    if not check:
        msg = str(err)
        Printf.err(f"DL Cover[{album.title}] failed: {msg}")
        return False, msg
    return True, ''


def downloadAlbumInfo(album, tracks):
    if album is None:
        return

    path = getAlbumPath(album)
    aigpy.path.mkdirs(path)

    path += '/AlbumInfo.txt'
    infos = ""
    infos += "[ID]          %s\n" % (str(album.id))
    infos += "[Title]       %s\n" % (str(album.title))
    infos += "[Artists]     %s\n" % (TIDAL_API.getArtistsName(album.artists))
    infos += "[ReleaseDate] %s\n" % (str(album.releaseDate))
    infos += "[SongNum]     %s\n" % (str(album.numberOfTracks))
    infos += "[Duration]    %s\n" % (str(album.duration))
    infos += '\n'

    for index in range(0, album.numberOfVolumes):
        volumeNumber = index + 1
        infos += f"===========CD {volumeNumber}=============\n"
        for item in tracks:
            if item.volumeNumber != volumeNumber:
                continue
            infos += '{:<8}'.format("[%d]" % item.trackNumber)
            infos += "%s\n" % item.title
    aigpy.file.write(path, infos, "w+")


def downloadVideo(video: Video, album: Album = None, playlist: Playlist = None):
    title = getattr(video, 'title', None) or str(getattr(video, 'id', 'unknown'))
    try:
        stream = TIDAL_API.getVideoStreamUrl(video.id, SETTINGS.videoQuality)
        path = getVideoPath(video, album, playlist)
        partPath = path + '.part'

        Printf.video(video, stream)
        logging.info("[DL Video] name=" + aigpy.path.getFileName(path) + "\nurl=" + stream.m3u8Url)

        __ensureParentDir__(path)
        __removeFile__(partPath)

        response = __httpRequest__("GET", stream.m3u8Url, allow_redirects=True)
        try:
            m3u8content = response.content
            if not m3u8content:
                Printf.err(f"DL Video[{title}] getM3u8 failed.")
                return False, "GetM3u8 failed."
        finally:
            response.close()

        urls = aigpy.m3u8.parseTsUrls(m3u8content)
        if len(urls) <= 0:
            Printf.err(f"DL Video[{title}] getTsUrls failed.")
            return False, "GetTsUrls failed."

        check, msg = __downloadUrls__(
            urls,
            partPath,
            SETTINGS.showProgress,
            threadNum=VIDEO_THREAD_COUNT,
            probeSize=False,
        )
        if check:
            os.replace(partPath, path)
            Printf.success(title)
            return True, ''
        else:
            __removeFile__(partPath)
            Printf.err(f"DL Video[{title}] failed.{msg}")
            return False, msg
    except Exception as e:
        __removeFile__(locals().get('partPath', ''))
        Printf.err(f"DL Video[{title}] failed.{str(e)}")
        return False, str(e)


def __getTrackStream__(track_id):
    priority = SETTINGS.getDownloadAudioQualityPriority()
    return TIDAL_API.getStreamUrlByPriority(track_id, priority)


def downloadTrack(track: Track, album=None, playlist=None, userProgress=None, partSize=DEFAULT_PART_SIZE):
    title = getattr(track, 'title', None) or str(getattr(track, 'id', 'unknown'))
    try:
        stream = __getTrackStream__(track.id)
        path = getTrackPath(track, stream, album, playlist)
        partPath = path + '.part'

        if SETTINGS.showTrackInfo and not SETTINGS.multiThread:
            Printf.track(track, stream)

        if userProgress is not None:
            userProgress.updateStream(stream)

        # check exist
        skipPath = __skipPath__(path, stream)
        if skipPath is not None:
            if SETTINGS.lyricFile:
                __saveLyricsForTrack__(track, skipPath)
            Printf.success(aigpy.path.getFileName(skipPath) + " (skip:already exists!)")
            return True, ''

        # download
        logging.info("[DL Track] name=" + aigpy.path.getFileName(path) + "\nurl=" + stream.url)

        __ensureParentDir__(path)
        __removeFile__(partPath)

        check, err = __downloadUrls__(
            stream.urls,
            partPath,
            SETTINGS.showProgress and not SETTINGS.multiThread,
            userProgress,
            TRACK_THREAD_COUNT if SETTINGS.multiThread else 1,
            max(int(partSize), 64 * 1024),
        )
        if not check:
            __removeFile__(partPath)
            __logFailedTrack__(track, album, playlist, err)
            Printf.err(f"DL Track '{title}' failed: {str(err)}{__downloadErrorHint__(err)}")
            return False, str(err)

        # encrypted -> decrypt and remove encrypted file
        __encrypted__(stream, partPath, path)
        path = __exportFlacFromContainer__(path, stream)

        # contributors
        try:
            contributors = TIDAL_API.getTrackContributors(track.id)
        except:
            contributors = None

        lyrics = __saveLyricsForTrack__(track, path)

        try:
            __setMetaData__(track, album, path, contributors, lyrics)
        except Exception as e:
            logging.warning("Unable to write metadata for %s: %s", path, e)
            Printf.info(f"Downloaded '{title}', but metadata tagging was skipped: {str(e)}")
        Printf.success(title)

        return True, ''
    except Exception as e:
        __removeFile__(locals().get('partPath', ''))
        __logFailedTrack__(track, album, playlist, e)
        Printf.err(f"DL Track '{title}' failed: {str(e)}{__downloadErrorHint__(e)}")
        return False, str(e)


def downloadTracks(tracks, album: Album = None, playlist: Playlist = None):
    albumCache = {}
    downloadedCovers = set()

    def __getAlbum__(item: Track):
        albumId = getattr(getattr(item, 'album', None), 'id', None)
        if albumId is None:
            return None

        if albumId not in albumCache:
            albumCache[albumId] = TIDAL_API.getAlbum(albumId)

        itemAlbum = albumCache[albumId]
        if SETTINGS.saveCovers and not SETTINGS.usePlaylistFolder and albumId not in downloadedCovers:
            downloadCover(itemAlbum)
            downloadedCovers.add(albumId)
        return itemAlbum

    if not SETTINGS.multiThread:
        success = True
        for index, item in enumerate(tracks):
            itemAlbum = album
            if itemAlbum is None:
                itemAlbum = __getAlbum__(item)
                item.trackNumberOnPlaylist = index + 1
            check, _ = downloadTrack(item, itemAlbum, playlist)
            success = success and check
        return success
    else:
        futures = []
        with ThreadPoolExecutor(max_workers=TRACK_THREAD_COUNT) as thread_pool:
            for index, item in enumerate(tracks):
                itemAlbum = album
                if itemAlbum is None:
                    itemAlbum = __getAlbum__(item)
                    item.trackNumberOnPlaylist = index + 1
                futures.append(thread_pool.submit(downloadTrack, item, itemAlbum, playlist))

            success = True
            for future in as_completed(futures):
                check, msg = future.result()
                if not check:
                    success = False
                    logging.error("Track download failed: %s", msg)
            return success


def downloadVideos(videos, album: Album, playlist=None):
    success = True
    for item in videos:
        check, _ = downloadVideo(item, album, playlist)
        success = success and check
    return success
