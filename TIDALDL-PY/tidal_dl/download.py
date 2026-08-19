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
        adapter = requests.adapters.HTTPAdapter(pool_connections=pool_size, pool_maxsize=pool_size, max_retries=3)
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


def __shouldRetryDownload__(error=None):
    """Retry connection failures and transient HTTP statuses, not 404/403/etc."""
    status = getattr(getattr(error, "response", None), "status_code", None)
    if status is None:
        return True
    return status in RETRYABLE_STATUS_CODES


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
            retry = attempt < DOWNLOAD_RETRIES - 1 and __shouldRetryDownload__(e)
            if response is not None:
                response.close()
            if retry:
                time.sleep(__retryDelay__(getattr(e, "response", None), attempt))
                continue
            raise
    raise last_error


def __parseIntHeader__(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def __contentRangeStart__(response):
    contentRange = response.headers.get("Content-Range", "")
    if not contentRange.lower().startswith("bytes "):
        return None
    try:
        return int(contentRange.split(" ", 1)[1].split("-", 1)[0])
    except (IndexError, ValueError):
        return None


def __contentTotalSize__(response):
    """Best-effort total object size from Content-Range or Content-Length."""
    if response is None:
        return -1
    contentRange = response.headers.get("Content-Range", "")
    if contentRange.lower().startswith("bytes ") and "/" in contentRange:
        total = contentRange.rsplit("/", 1)[-1].strip()
        if total != "*":
            size = __parseIntHeader__(total)
            if size > 0:
                return size
    if response.status_code == 200:
        size = __parseIntHeader__(response.headers.get("Content-Length"))
        if size > 0:
            return size
    return -1


def __contentLength__(url):
    """Probe remote size via HEAD, falling back to a 1-byte Range GET."""
    try:
        response = __httpRequest__("HEAD", url, allow_redirects=True)
        try:
            size = __parseIntHeader__(response.headers.get("Content-Length"))
            if size > 0:
                return size
            size = __contentTotalSize__(response)
            if size > 0:
                return size
        finally:
            response.close()
    except Exception:
        pass

    # Some CDNs reject HEAD; a tiny ranged GET still exposes total size.
    try:
        response = __httpRequest__(
            "GET",
            url,
            allow_redirects=True,
            stream=True,
            headers={"Range": "bytes=0-0"},
        )
        try:
            size = __contentTotalSize__(response)
            if size > 0:
                return size
            size = __parseIntHeader__(response.headers.get("Content-Length"))
            return size if size > 0 else -1
        finally:
            response.close()
    except Exception:
        return -1


def __remoteSize__(urls):
    if isinstance(urls, str):
        urls = [urls]
    urls = list(urls or [])
    if not urls:
        return 0
    if len(urls) == 1:
        size = __contentLength__(urls[0])
        return size if size > 0 else -1

    # Probe segment sizes in parallel; serial HEAD requests dominated
    # startup time for DASH tracks with many segments.
    total = 0
    with ThreadPoolExecutor(max_workers=min(8, len(urls))) as probe_pool:
        for size in probe_pool.map(__contentLength__, urls):
            if size <= 0:
                return -1
            total += size
    return total


def __localFileSize__(path):
    return aigpy.file.getSize(path) if path else 0


def __isCompleteLocalFile__(path, expectedSize=-1):
    """True when ``path`` is a finished object.

    If ``expectedSize`` is known, require an exact match. If unknown, only treat
    the file as finished when there is no ``.download`` resume sidecar (used for
    multi-segment parts that already completed in a prior attempt).
    """
    size = __localFileSize__(path)
    if size <= 0:
        return False
    # A leftover .download sidecar means the last transfer did not finish cleanly.
    if __localFileSize__(path + ".download") > 0:
        return False
    if expectedSize > 0:
        return size == expectedSize
    return True


def __isReusableAssembledFile__(path, expectedSize=-1):
    """Stricter check for assembled outputs: never skip when size is unknown."""
    if expectedSize is None or expectedSize <= 0:
        return False
    return __isCompleteLocalFile__(path, expectedSize)


def __verifyLocalSize__(path, expectedSize, label="download"):
    if expectedSize is None or expectedSize <= 0:
        return __localFileSize__(path)
    actual = __localFileSize__(path)
    if actual != expectedSize:
        raise IOError(
            f"Incomplete {label}: got {actual} bytes, expected {expectedSize}"
        )
    return actual


def __setUserProgressMax__(userProgress, size):
    if userProgress is None or size <= 0:
        return
    try:
        userProgress.setMaxNum(size)
    except Exception:
        pass


def __addUserProgress__(userProgress, size, progressLock=None):
    if userProgress is None or size <= 0:
        return
    try:
        if progressLock is not None:
            with progressLock:
                userProgress.addCurNum(size)
        else:
            userProgress.addCurNum(size)
    except Exception:
        pass


def __noteProgress__(progress, userProgress, size, progressLock=None):
    if size <= 0:
        return
    if progressLock is not None:
        with progressLock:
            if progress is not None:
                try:
                    progress.addCurCount(size)
                except Exception:
                    pass
            __addUserProgress__(userProgress, size)
        return
    if progress is not None:
        try:
            progress.addCurCount(size)
        except Exception:
            pass
    __addUserProgress__(userProgress, size)


def __downloadSingleUrl__(
        url,
        outputPath,
        progress=None,
        userProgress=None,
        chunkSize=DOWNLOAD_CHUNK_SIZE,
        progressLock=None,
        expectedSize=-1,
        allowUnknownSizeReuse=False):
    """Download one CDN URL to outputPath with HTTP Range resume.

    Partial progress is kept in ``outputPath + '.download'`` until the transfer
    finishes, then moved into place with ``os.replace`` so callers never see a
    half-written final file. When ``expectedSize`` or response headers expose a
    total size, the finished file is verified before it is promoted.
    """
    # When expectedSize is known, require an exact match. Multi-segment parts may
    # also reuse a finished object when size is unknown (prior successful segment
    # write). Top-level single-URL downloads must not skip just because a local
    # file exists — that path might be an unrelated leftover.
    if expectedSize > 0:
        reusable = __isCompleteLocalFile__(outputPath, expectedSize)
    elif allowUnknownSizeReuse:
        reusable = (
            __localFileSize__(outputPath) > 0
            and __localFileSize__(outputPath + ".download") <= 0
        )
    else:
        reusable = False
    if reusable:
        __noteProgress__(
            progress, userProgress, __localFileSize__(outputPath), progressLock
        )
        return __localFileSize__(outputPath)

    tempOutputPath = outputPath + ".download"
    reportedBytes = 0
    lastError = None
    knownTotal = expectedSize if expectedSize and expectedSize > 0 else -1

    for attempt in range(DOWNLOAD_RETRIES):
        resumeSize = __localFileSize__(tempOutputPath)
        headers = {"Range": f"bytes={resumeSize}-"} if resumeSize > 0 else {}
        response = None
        try:
            response = __httpRequest__("GET", url, stream=True, allow_redirects=True, headers=headers)
            mode = "wb"
            if resumeSize > 0:
                rangeStart = __contentRangeStart__(response)
                if response.status_code == 206 and rangeStart == resumeSize:
                    mode = "ab"
                    credit = max(resumeSize - reportedBytes, 0)
                    if credit:
                        __noteProgress__(progress, userProgress, credit, progressLock)
                        reportedBytes = resumeSize
                elif response.status_code == 200:
                    # Server ignored Range and returned the full object; restart.
                    __removeFile__(tempOutputPath)
                    resumeSize = 0
                    mode = "wb"
                else:
                    # Mismatched partial response: drop partial and re-GET fully.
                    response.close()
                    response = None
                    __removeFile__(tempOutputPath)
                    resumeSize = 0
                    response = __httpRequest__("GET", url, stream=True, allow_redirects=True)
                    mode = "wb"

            responseTotal = __contentTotalSize__(response)
            if responseTotal > 0:
                knownTotal = responseTotal
            elif response.status_code == 200:
                contentLength = __parseIntHeader__(response.headers.get("Content-Length"))
                if contentLength > 0:
                    knownTotal = contentLength

            with open(tempOutputPath, mode) as output:
                for chunk in response.iter_content(chunk_size=chunkSize):
                    if not chunk:
                        continue
                    output.write(chunk)
                    __noteProgress__(progress, userProgress, len(chunk), progressLock)
                    reportedBytes += len(chunk)

            __verifyLocalSize__(tempOutputPath, knownTotal, label="CDN object")
            os.replace(tempOutputPath, outputPath)
            return __localFileSize__(outputPath)
        except (requests.RequestException, OSError, IOError) as error:
            lastError = error
            if attempt >= DOWNLOAD_RETRIES - 1 or not __shouldRetryDownload__(error):
                raise
            time.sleep(__retryDelay__(response, attempt))
        finally:
            if response is not None:
                response.close()

    raise lastError


def __concatenateFiles__(partPaths, outputPath, expectedSize=-1):
    tempOutputPath = f"{outputPath}.tmp.{os.getpid()}"
    __removeFile__(tempOutputPath)
    try:
        with open(tempOutputPath, "wb") as output:
            for partPath in partPaths:
                with open(partPath, "rb") as inputFile:
                    shutil.copyfileobj(inputFile, output)
        __verifyLocalSize__(tempOutputPath, expectedSize, label="assembled media")
        os.replace(tempOutputPath, outputPath)
    except Exception:
        __removeFile__(tempOutputPath)
        raise


def __partsDirectory__(outputPath):
    # Stable across retries so multi-segment DASH can resume after a failure.
    return f"{outputPath}.parts"


def __downloadSegment__(
        url,
        partPath,
        progress=None,
        userProgress=None,
        progressLock=None,
        chunkSize=DOWNLOAD_CHUNK_SIZE,
        expectedSize=-1):
    return __downloadSingleUrl__(
        url,
        partPath,
        progress=progress,
        userProgress=userProgress,
        chunkSize=chunkSize,
        progressLock=progressLock,
        expectedSize=expectedSize,
        allowUnknownSizeReuse=True,
    )


def __downloadUrls__(
        urls,
        outputPath,
        showProgress=False,
        userProgress=None,
        threadNum=1,
        chunkSize=DOWNLOAD_CHUNK_SIZE,
        probeSize=True,
        expectedSize=None):
    urls = [url for url in (urls or []) if not aigpy.string.isNull(url)]
    if len(urls) <= 0:
        return False, "URL list is empty."

    __ensureParentDir__(outputPath)

    if expectedSize is not None:
        totalSize = expectedSize
    elif probeSize:
        totalSize = __remoteSize__(urls)
    else:
        totalSize = -1
    progress = None
    if totalSize > 0:
        __setUserProgressMax__(userProgress, totalSize)
        if showProgress:
            progress = aigpy.progress.ProgressTool(totalSize, 15, unit="B")

    # Already-complete assembled file (e.g. decrypt failed after CDN success).
    # Only reuse when the remote size is known and matches — never skip a
    # download solely because a local file happens to exist.
    if __isReusableAssembledFile__(outputPath, totalSize):
        __noteProgress__(progress, userProgress, __localFileSize__(outputPath))
        __removeDir__(__partsDirectory__(outputPath))
        return True, ''

    if len(urls) == 1:
        try:
            __downloadSingleUrl__(
                urls[0],
                outputPath,
                progress,
                userProgress,
                chunkSize,
                expectedSize=totalSize,
            )
            return True, ''
        except Exception as e:
            return False, str(e)

    # Multi-segment (DASH / HLS): resumeable per-segment downloads, ordered concat.
    partsDir = __partsDirectory__(outputPath)
    os.makedirs(partsDir, exist_ok=True)
    progressLock = Lock()
    workers = 1 if threadNum <= 1 else min(threadNum, len(urls))
    partPaths = [os.path.join(partsDir, f"{index:08d}.part") for index in range(len(urls))]

    try:
        if workers == 1:
            for url, partPath in zip(urls, partPaths):
                __downloadSegment__(
                    url,
                    partPath,
                    progress,
                    userProgress,
                    None,
                    chunkSize,
                )
        else:
            with ThreadPoolExecutor(max_workers=workers) as thread_pool:
                futures = {
                    thread_pool.submit(
                        __downloadSegment__,
                        url,
                        partPath,
                        progress,
                        userProgress,
                        progressLock,
                        chunkSize,
                    ): index
                    for index, (url, partPath) in enumerate(zip(urls, partPaths))
                }
                try:
                    for future in as_completed(futures):
                        future.result()
                except Exception:
                    for pending in futures:
                        pending.cancel()
                    raise

        __concatenateFiles__(partPaths, outputPath, expectedSize=totalSize)
        __removeDir__(partsDir)
        return True, ''
    except Exception as e:
        # Keep complete segments under outputPath.parts for the next attempt.
        return False, str(e)


def __isSkip__(finalpath, urls):
    if not SETTINGS.checkExist:
        return False
    curSize = __localFileSize__(finalpath)
    if curSize <= 0:
        return False
    if __localFileSize__(finalpath + ".download") > 0:
        return False
    netSize = __remoteSize__(urls)
    if netSize <= 0:
        return False
    return curSize >= netSize


def __downloadErrorHint__(err):
    text = str(err or "").lower()
    if any(item in text for item in ("429", "too many requests", "rate limit")):
        return " (hint: raise the request interval in settings and retry)"
    if any(item in text for item in ("4022", "client referenced", "log in again")):
        return " (hint: your saved login session is stale; log out, log in again, then retry)"
    if "prerequisite" in text:
        return " (hint: this quality may be unavailable to this app for your account; set a fallback order, e.g. --quality-priority Max,HiFi,High,Normal)"
    if any(item in text for item in ("403", "entitled", "not allowed", "client_not_entitled")):
        return " (hint: stream may be unavailable for this account or quality; try a lower quality/fallback order)"
    if "incomplete" in text and "expected" in text:
        return " (hint: retry the download; a partial transfer was discarded after size verification failed)"
    if any(item in text for item in ("timeout", "connection", "network", "name or service not known")):
        return " (hint: check network/VPN/proxy/firewall, or run tidekeeper --doctor)"
    if any(item in text for item in ("permission", "denied", "access is denied", "readonly")):
        return " (hint: choose a writable download folder outside protected system directories)"
    if "disk" in text or "space" in text or "no space" in text:
        return " (hint: check available disk space)"
    if any(item in text for item in ("not ready for streaming", "not ready for playback", "asset is not ready")):
        return " (hint: retry later, raise the request interval in settings, or try a lower quality)"
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


def __looksLikeCompleteAudio__(path, minimum=1024):
    size = aigpy.file.getSize(path)
    if size < minimum:
        return False
    try:
        with open(path, "rb") as handle:
            header = handle.read(4)
    except OSError:
        return False
    if path.lower().endswith(".flac"):
        return header == b"fLaC"
    return True


def __skipPath__(path, stream):
    if __isSkip__(path, stream.urls):
        return path

    if not SETTINGS.checkExist:
        return None

    if SETTINGS.saveAsFlac and __isFlacInM4a__(stream):
        for candidate in (path, __containerFallbackPath__(path)):
            if __looksLikeCompleteAudio__(candidate):
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


def __iterArtists__(artists):
    # TIDAL omits `artists` for some items (aigpy then stores None) and the
    # models default to a single prototype instance, so the attribute is not
    # always an iterable list of artists (issue #38).
    if isinstance(artists, (list, tuple)):
        return [artist for artist in artists if artist is not None]
    return []


def __rawArtistNames__(artists):
    return [
        str(getattr(artist, 'name', '')).strip()
        for artist in __iterArtists__(artists)
        if getattr(artist, 'name', None)
    ]


def __artistNames__(artists):
    return [
        __normalizeLyricsMatchText__(getattr(artist, 'name', ''))
        for artist in __iterArtists__(artists)
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
        return [item['name'] for item in Contributors['items'] if item['role'] == roleType]
    except (KeyError, TypeError):
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


def __metadataArtistNames__(item):
    """Return tag artist names, falling back to the item's primary artist."""
    names = __rawArtistNames__(getattr(item, 'artists', None))
    if names:
        return names
    artist = getattr(item, 'artist', None)
    name = getattr(artist, 'name', None) if artist is not None else None
    return [str(name).strip()] if name else []


def __setMetaData__(track: Track, album: Album, filepath, contributors, lyrics):
    obj = aigpy.tag.TagTool(filepath)
    obj.album = track.album.title
    obj.title = track.title
    if not aigpy.string.isNull(track.version):
        obj.title += f' ({track.version})'

    obj.artist = __metadataArtistNames__(track)
    obj.copyright = track.copyRight
    obj.tracknumber = track.trackNumber
    obj.discnumber = track.volumeNumber
    obj.composer = __parseContributors__('Composer', contributors)
    obj.isrc = track.isrc

    obj.albumartist = __metadataArtistNames__(album)
    obj.date = album.releaseDate
    obj.totaldisc = int(getattr(album, 'numberOfVolumes', 0) or 0)
    obj.lyrics = lyrics
    if obj.totaldisc <= 1:
        obj.totaltrack = int(getattr(album, 'numberOfTracks', 0) or 0)
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
    infos = (
        f"[ID]          {album.id}\n"
        f"[Title]       {album.title}\n"
        f"[Artists]     {TIDAL_API.getArtistsName(album.artists)}\n"
        f"[ReleaseDate] {album.releaseDate}\n"
        f"[SongNum]     {album.numberOfTracks}\n"
        f"[Duration]    {album.duration}\n"
        "\n"
    )

    for index in range(album.numberOfVolumes):
        volumeNumber = index + 1
        infos += f"===========CD {volumeNumber}=============\n"
        for item in tracks:
            if item.volumeNumber != volumeNumber:
                continue
            infos += f"{f'[{item.trackNumber}]':<8}{item.title}\n"
    aigpy.file.write(path, infos, "w+")


def __finalizeVideoFile__(partPath, path):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        logging.warning("ffmpeg not found; saving concatenated MPEG-TS as %s", path)
        os.replace(partPath, path)
        Printf.info("Install ffmpeg to remux videos into playable MP4 files.")
        return path

    tempPath = f"{path}.tmp.{os.getpid()}.mp4"
    __removeFile__(tempPath)
    command = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        partPath,
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        tempPath,
    ]
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode == 0 and __localFileSize__(tempPath) > 0:
            os.replace(tempPath, path)
            __removeFile__(partPath)
            return path
        logging.warning(
            "ffmpeg remux failed (%s); keeping concatenated stream as %s",
            (completed.stderr or b"").decode("utf-8", "ignore").strip(),
            path,
        )
    except OSError as error:
        logging.warning("ffmpeg remux failed: %s", error)
    __removeFile__(tempPath)
    os.replace(partPath, path)
    return path


def downloadVideo(video: Video, album: Album = None, playlist: Playlist = None, userProgress=None):
    title = getattr(video, 'title', None) or str(getattr(video, 'id', 'unknown'))
    partPath = ''
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
            userProgress,
            VIDEO_THREAD_COUNT,
            probeSize=False,
        )
        if check:
            path = __finalizeVideoFile__(partPath, path)
            Printf.success(title)
            return True, ''
        else:
            __removeFile__(partPath)
            Printf.err(f"DL Video[{title}] failed.{msg}")
            return False, msg
    except Exception as e:
        __removeFile__(partPath)
        Printf.err(f"DL Video[{title}] failed.{str(e)}")
        return False, str(e)


def __getTrackStream__(track_id):
    priority = SETTINGS.getDownloadAudioQualityPriority()
    return TIDAL_API.getStreamUrlByPriority(track_id, priority)


def __wantsAtmosDownload__():
    return any(quality == AudioQuality.Atmos for quality in SETTINGS.getDownloadAudioQualityPriority())


def __resolveTrackForAtmosDownload__(track: Track, album=None):
    """Swap stereo catalog IDs for Atmos twins when Atmos quality is requested.

    Covers album, track, playlist, and mix paths — not only start_track().
    """
    if track is None or not __wantsAtmosDownload__():
        return track, album
    if TIDAL_API.__hasAtmosMode__(track):
        return track, album

    atmos = TIDAL_API.findAtmosTrackVariant(track)
    if atmos is None or str(getattr(atmos, 'id', '')) == str(getattr(track, 'id', '')):
        return track, album

    Printf.info(
        f"Using Dolby Atmos track {atmos.id} "
        f"(stereo catalog id was {track.id})."
    )

    atmos_album = album
    atmos_album_id = getattr(getattr(atmos, 'album', None), 'id', None)
    album_id = getattr(album, 'id', None) if album is not None else None
    if atmos_album_id is not None and str(atmos_album_id) != str(album_id or ''):
        try:
            atmos_album = TIDAL_API.getAlbum(atmos_album_id)
        except Exception:
            atmos_album = album
    return atmos, atmos_album


def __ensureTrackStreamable__(track):
    if getattr(track, 'allowStreaming', None) is False:
        raise Exception("Track is not available for streaming on this account.")
    if getattr(track, 'streamReady', None) is False:
        raise Exception("Track is not ready for streaming yet. Try again later.")


def downloadTrack(track: Track, album=None, playlist=None, userProgress=None, partSize=DEFAULT_PART_SIZE):
    """Resolve stream → download CDN bytes → decrypt → tag.

    Pipeline:
      1. Quality priority + OpenAPI/playback fallback (``getStreamUrlByPriority``)
      2. Skip if a complete file already exists (size vs remote Content-Length)
      3. Download to ``path.part`` with Range resume / multi-segment concat
      4. AES-CTR decrypt when encryptionKey is present (chunked, not whole-file)
      5. Optional ffmpeg FLAC remux, lyrics sidecar, metadata tags
    """
    title = getattr(track, 'title', None) or str(getattr(track, 'id', 'unknown'))
    partPath = ''
    try:
        track, album = __resolveTrackForAtmosDownload__(track, album)
        title = getattr(track, 'title', None) or str(getattr(track, 'id', 'unknown'))
        __ensureTrackStreamable__(track)
        stream = __getTrackStream__(track.id)
        path = getTrackPath(track, stream, album, playlist)
        partPath = path + '.part'
        partsDir = __partsDirectory__(partPath)

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

        # Reuse a complete assembled part from a previous attempt (e.g. decrypt
        # failed after a successful CDN transfer). Otherwise download/resume.
        expectedSize = __remoteSize__(stream.urls)
        if __isReusableAssembledFile__(partPath, expectedSize):
            check, err = True, ''
        else:
            # Incomplete assembled part is not useful; resume lives in sidecars /
            # outputPath.parts instead.
            if __localFileSize__(partPath) > 0 and not __isReusableAssembledFile__(partPath, expectedSize):
                __removeFile__(partPath)
            check, err = __downloadUrls__(
                stream.urls,
                partPath,
                SETTINGS.showProgress and not SETTINGS.multiThread,
                userProgress,
                TRACK_THREAD_COUNT if SETTINGS.multiThread else 1,
                max(int(partSize), 64 * 1024),
                False,
                expectedSize,
            )
        if not check:
            __logFailedTrack__(track, album, playlist, err)
            Printf.err(f"DL Track '{title}' failed: {str(err)}{__downloadErrorHint__(err)}")
            return False, str(err)

        # encrypted -> decrypt and remove encrypted file.
        # On failure, the outer handler keeps a complete partPath for retry.
        __encrypted__(stream, partPath, path)
        __removeDir__(partsDir)
        path = __exportFlacFromContainer__(path, stream)

        # contributors
        try:
            contributors = TIDAL_API.getTrackContributors(track.id)
        except Exception:
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
        # Preserve complete/partial transfer state for resume; only drop empty parts.
        if partPath and __localFileSize__(partPath) <= 0:
            __removeFile__(partPath)
        __logFailedTrack__(track, album, playlist, e)
        Printf.err(f"DL Track '{title}' failed: {str(e)}{__downloadErrorHint__(e)}")
        return False, str(e)


def downloadTracks(tracks, album: Album = None, playlist: Playlist = None, progress=None):
    albumCache = {}
    downloadedCovers = set()
    tracks = list(tracks or [])
    total = len(tracks)
    if progress is not None and total:
        progress.begin_collection(total)

    def __getAlbum__(item: Track):
        albumId = getattr(getattr(item, 'album', None), 'id', None)
        if albumId is None:
            return None

        if albumId not in albumCache:
            try:
                albumCache[albumId] = TIDAL_API.getAlbum(albumId)
            except Exception as error:
                logging.warning("Unable to load album %s for playlist track: %s", albumId, error)
                albumCache[albumId] = None

        itemAlbum = albumCache[albumId]
        if SETTINGS.saveCovers and not SETTINGS.usePlaylistFolder and albumId not in downloadedCovers:
            downloadCover(itemAlbum)
            downloadedCovers.add(albumId)
        return itemAlbum

    def __trackProgressKwargs__():
        if progress is None:
            return {}
        return {"userProgress": progress}

    if not SETTINGS.multiThread:
        success = True
        for index, item in enumerate(tracks):
            itemAlbum = album
            if itemAlbum is None:
                itemAlbum = __getAlbum__(item)
                item.trackNumberOnPlaylist = index + 1
            if progress is not None:
                progress.begin_entry(index + 1, total, getattr(item, 'title', '') or '')
            check, _ = downloadTrack(item, itemAlbum, playlist, **__trackProgressKwargs__())
            if progress is not None:
                progress.finish_entry(index + 1, total, check)
            success = success and check
        return success
    else:
        futures = {}
        with ThreadPoolExecutor(max_workers=TRACK_THREAD_COUNT) as thread_pool:
            for index, item in enumerate(tracks):
                itemAlbum = album
                if itemAlbum is None:
                    itemAlbum = __getAlbum__(item)
                    item.trackNumberOnPlaylist = index + 1
                if progress is not None:
                    progress.begin_entry(index + 1, total, getattr(item, 'title', '') or '')
                futures[thread_pool.submit(
                    downloadTrack,
                    item,
                    itemAlbum,
                    playlist,
                    **__trackProgressKwargs__(),
                )] = index

            success = True
            for future in as_completed(futures):
                index = futures[future]
                check, msg = future.result()
                if progress is not None:
                    progress.finish_entry(index + 1, total, check)
                if not check:
                    success = False
                    logging.error("Track download failed: %s", msg)
            return success


def downloadVideos(videos, album: Album, playlist=None, progress=None):
    videos = list(videos or [])
    total = len(videos)
    if progress is not None and total:
        progress.begin_collection(total)
    success = True
    for index, item in enumerate(videos):
        if progress is not None:
            progress.begin_entry(index + 1, total, getattr(item, 'title', '') or '')
        kwargs = {}
        if progress is not None:
            kwargs["userProgress"] = progress
        check, _ = downloadVideo(item, album, playlist, **kwargs)
        if progress is not None:
            progress.finish_entry(index + 1, total, check)
        success = success and check
    return success
