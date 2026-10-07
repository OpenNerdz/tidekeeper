#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@File    :  events.py
@Date    :  2022/06/10
@Author  :  Yaronzz
@Version :  1.0
@Contact :  yaronhuang@foxmail.com
@Desc    :
"""

from .runtime import print, check_cancelled, DownloadCancelled, sleep as cancellable_sleep
import logging
import math
import time

import aigpy

from . import apiKey
from .enums import AUDIO_QUALITY_ORDER, AudioQuality, Type, VideoQuality
from .inputs import parse_direct_inputs
from .lang.language import LANG
from .model import Album, Artist, Mix, Playlist, Track, Video
from .paths import legacyDownloadNotice, migrateLegacyDownloads
from .printf import Printf
from .settings import SETTINGS, TOKEN, syncPlaybackRateLimiter
from .tidal import TIDAL_API
from .download import (
    _wantsAtmosDownload, downloadAlbumInfo, downloadCover, downloadTrack,
    downloadTracks, downloadVideo, downloadVideos,
)

# --------------------------------------------------------------- downloads


def _resolveAlbumForDownload(obj: Album) -> Album:
    """Prefer the Atmos catalog twin when Atmos quality is requested."""
    if obj is None or not _wantsAtmosDownload():
        return obj
    if TIDAL_API._hasAtmosMode(obj):
        return obj
    atmos = TIDAL_API.findAtmosAlbumVariant(obj)
    if atmos is None or str(getattr(atmos, "id", "")) == str(getattr(obj, "id", "")):
        return obj
    Printf.info(
        f"Using Dolby Atmos catalog release {atmos.id} "
        f"(stereo search result was {obj.id})."
    )
    return atmos


def _preferAtmosAlbums(albums):
    """When Atmos is requested, skip stereo albums that already have an Atmos twin in the list."""
    if not albums or not _wantsAtmosDownload():
        return albums

    atmos_titles = {
        TIDAL_API._normalizeCatalogTitle(getattr(album, "title", None))
        for album in albums
        if TIDAL_API._hasAtmosMode(album)
    }
    preferred = []
    for album in albums:
        title = TIDAL_API._normalizeCatalogTitle(getattr(album, "title", None))
        if (
            title
            and title in atmos_titles
            and not TIDAL_API._hasAtmosMode(album)
        ):
            continue
        preferred.append(album)
    return preferred


def _progress_kwargs(progress):
    return {"progress": progress} if progress is not None else {}


def start_album(obj: Album, videoOnly=False, progress=None):
    obj = _resolveAlbumForDownload(obj)
    Printf.album(obj)
    tracks, videos = TIDAL_API.getItems(obj.id, Type.Album)
    if hasattr(progress, 'plan_collection'):
        progress.plan_collection((len(tracks) if not videoOnly else 0) +
                                 (len(videos) if videoOnly or SETTINGS.downloadVideos else 0))
    success = True
    if not videoOnly and SETTINGS.saveAlbumInfo:
        downloadAlbumInfo(obj, tracks)
    if not videoOnly and SETTINGS.saveCovers and obj.cover is not None:
        downloadCover(obj)
    if not videoOnly:
        success = downloadTracks(tracks, obj, **_progress_kwargs(progress)) and success
    if videoOnly or SETTINGS.downloadVideos:
        success = downloadVideos(videos, obj, **_progress_kwargs(progress)) and success
    return success


def start_track(obj: Track, progress=None):
    # downloadTrack resolves Atmos twins for album/track/playlist/mix paths.
    album = None
    album_id = getattr(getattr(obj, "album", None), "id", None)
    if album_id is not None:
        album = TIDAL_API.getAlbum(album_id)
        if SETTINGS.saveCovers:
            downloadCover(album)
    kwargs = {"userProgress": progress} if progress is not None else {}
    check, _ = downloadTrack(obj, album, **kwargs)
    return check


def start_video(obj: Video, progress=None):
    kwargs = {"userProgress": progress} if progress is not None else {}
    check, _ = downloadVideo(obj, obj.album, **kwargs)
    return check


def start_artist(obj: Artist, videoOnly=False, progress=None):
    if videoOnly:
        videos = TIDAL_API.getArtistVideos(obj.id)
        Printf.artist(obj, len(videos), "Number of videos")
        if len(videos) <= 0:
            Printf.info("No videos found for artist.")
            return False
        return downloadVideos(videos, None, **_progress_kwargs(progress))

    albums = _preferAtmosAlbums(TIDAL_API.getArtistAlbums(obj.id, SETTINGS.includeEP))
    Printf.artist(obj, len(albums))
    success = True
    for item in albums:
        check_cancelled()
        success = start_album(item, progress=progress) and success
    return success


def start_playlist(obj: Playlist, videoOnly=False, progress=None):
    Printf.playlist(obj)
    tracks, videos = TIDAL_API.getItems(obj.uuid, Type.Playlist)
    if hasattr(progress, 'plan_collection'):
        progress.plan_collection((len(tracks) if not videoOnly else 0) +
                                 (len(videos) if videoOnly or SETTINGS.downloadVideos else 0))
    success = True
    if not videoOnly:
        success = downloadTracks(tracks, None, obj, **_progress_kwargs(progress)) and success
    if videoOnly or SETTINGS.downloadVideos:
        success = downloadVideos(videos, None, obj, **_progress_kwargs(progress)) and success
    return success


def start_mix(obj: Mix, videoOnly=False, progress=None):
    Printf.mix(obj)
    success = True
    if not videoOnly:
        success = downloadTracks(obj.tracks, None, None, **_progress_kwargs(progress)) and success
    if videoOnly or SETTINGS.downloadVideos:
        success = downloadVideos(obj.videos, None, None, **_progress_kwargs(progress)) and success
    return success


_legacyNoticeShown = False


def _showLegacyDownloadNotice():
    """Migrate discoverable downloads saved in a literal '~' folder once per run."""
    global _legacyNoticeShown
    if _legacyNoticeShown:
        return
    _legacyNoticeShown = True
    try:
        migration = migrateLegacyDownloads()
    except (OSError, ValueError) as error:
        migration = None
        Printf.info(f'Could not migrate earlier downloads automatically: {error}')
    if migration:
        Printf.info(migration)
    notice = legacyDownloadNotice()
    if notice:
        Printf.info(notice)


def start_type(etype: Type, obj, videoOnly=False, progress=None):
    _showLegacyDownloadNotice()
    if etype == Type.Album:
        return start_album(obj, videoOnly, progress=progress)
    if etype == Type.Track:
        if videoOnly:
            Printf.err("Video-only downloads require an artist, album, playlist, mix, or video URL.")
            return False
        return start_track(obj, progress=progress)
    if etype == Type.Video:
        return start_video(obj, progress=progress)
    if etype == Type.Artist:
        return start_artist(obj, videoOnly, progress=progress)
    if etype == Type.Playlist:
        return start_playlist(obj, videoOnly, progress=progress)
    if etype == Type.Mix:
        return start_mix(obj, videoOnly, progress=progress)
    return False


def start(string, videoOnly=False, progress=None):
    if aigpy.string.isNull(string):
        Printf.err('Please enter something.')
        return False

    try:
        strings = parse_direct_inputs(string)
    except (OSError, ValueError) as error:
        Printf.err(str(error))
        return False
    success = True
    sawItem = False
    for item in strings:
        check_cancelled()
        sawItem = True
        try:
            etype, obj = TIDAL_API.getByString(item)
        except DownloadCancelled:
            raise
        except Exception as e:
            Printf.err(str(e) + " [" + item + "]")
            success = False
            continue

        try:
            if not start_type(etype, obj, videoOnly, progress=progress):
                success = False
        except DownloadCancelled:
            raise
        except Exception as e:
            Printf.err(str(e))
            success = False
    return success if sawItem else False


# ---------------------------------------------------------------- settings


def changePathSettings():
    Printf.settings()
    SETTINGS.downloadPath = Printf.enterPath(
        LANG.select.CHANGE_DOWNLOAD_PATH,
        LANG.select.MSG_PATH_ERR,
        '0',
        SETTINGS.downloadPath)
    SETTINGS.albumFolderFormat = Printf.enterFormat(
        LANG.select.CHANGE_ALBUM_FOLDER_FORMAT,
        SETTINGS.albumFolderFormat,
        SETTINGS.getDefaultPathFormat(Type.Album))
    SETTINGS.playlistFolderFormat = Printf.enterFormat(
        LANG.select.CHANGE_PLAYLIST_FOLDER_FORMAT,
        SETTINGS.playlistFolderFormat,
        SETTINGS.getDefaultPathFormat(Type.Playlist))
    SETTINGS.trackFileFormat = Printf.enterFormat(
        LANG.select.CHANGE_TRACK_FILE_FORMAT,
        SETTINGS.trackFileFormat,
        SETTINGS.getDefaultPathFormat(Type.Track))
    SETTINGS.videoFileFormat = Printf.enterFormat(
        LANG.select.CHANGE_VIDEO_FILE_FORMAT,
        SETTINGS.videoFileFormat,
        SETTINGS.getDefaultPathFormat(Type.Video))
    SETTINGS.save()


def changeQualitySettings():
    Printf.settings()
    audio_choices = ", ".join(f"'{item.value}'-{item.name}" for item in AUDIO_QUALITY_ORDER)
    selected_quality = AudioQuality(
        int(Printf.enterLimit(f"{LANG.select.SETTING_AUDIO_QUALITY} ({audio_choices}):",
                              LANG.select.MSG_INPUT_ERR,
                              [str(item.value) for item in AUDIO_QUALITY_ORDER])))
    priority = Printf.enter(
        "Fallback qualities comma list, blank for selected quality only, e.g. HiFi,High,Normal:"
    )
    fallbacks = SETTINGS.getAudioQualityPriority(priority)
    SETTINGS.audioQuality = selected_quality
    SETTINGS.audioQualityPriority = (
        [selected_quality] + [item for item in fallbacks if item != selected_quality]
        if fallbacks else []
    )
    SETTINGS.videoQuality = VideoQuality(
        int(Printf.enterLimit(f"{LANG.select.SETTING_VIDEO_QUALITY} "
                              f"({', '.join(str(item.value) for item in reversed(VideoQuality))}):",
                              LANG.select.MSG_INPUT_ERR,
                              [str(item.value) for item in reversed(VideoQuality)])))
    SETTINGS.save()


def changeSettings():
    Printf.settings()
    SETTINGS.showProgress = Printf.enterBool(LANG.select.CHANGE_SHOW_PROGRESS)
    SETTINGS.showTrackInfo = Printf.enterBool(LANG.select.CHANGE_SHOW_TRACKINFO)
    SETTINGS.checkExist = Printf.enterBool(LANG.select.CHANGE_CHECK_EXIST)
    SETTINGS.includeEP = Printf.enterBool(LANG.select.CHANGE_INCLUDE_EP)
    SETTINGS.saveCovers = Printf.enterBool(LANG.select.CHANGE_SAVE_COVERS)
    SETTINGS.saveAlbumInfo = Printf.enterBool(LANG.select.CHANGE_SAVE_ALBUM_INFO)
    SETTINGS.downloadVideos = Printf.enterBool(LANG.select.CHANGE_DOWNLOAD_VIDEOS)
    SETTINGS.lyricFile = Printf.enterBool(LANG.select.CHANGE_ADD_LRC_FILE)
    SETTINGS.multiThread = Printf.enterBool(LANG.select.CHANGE_MULITHREAD_DOWNLOAD)
    if SETTINGS.multiThread:
        try:
            tracks = min(8, max(1, int(Printf.enter("Concurrent tracks (1-8):"))))
            segments = min(8, max(1, int(Printf.enter("Segments per track (1-8):"))))
            SETTINGS.concurrentTracks, SETTINGS.segmentsPerTrack = tracks, segments
        except (TypeError, ValueError):
            Printf.info("Keeping existing concurrency limits.")
    SETTINGS.usePlaylistFolder = Printf.enterBool(LANG.select.SETTING_USE_PLAYLIST_FOLDER + "('0'-No,'1'-Yes):")
    SETTINGS.downloadDelay = Printf.enterBool(LANG.select.CHANGE_USE_DOWNLOAD_DELAY)
    interval = Printf.enter(LANG.select.CHANGE_REQUEST_INTERVAL_SECONDS)
    try:
        seconds = float(interval)
        if not math.isfinite(seconds) or not 0 <= seconds <= 300:
            raise ValueError('Delay must be between 0 and 300 seconds.')
        SETTINGS.requestIntervalSeconds = seconds
    except (TypeError, ValueError):
        Printf.info("Keeping existing request delay seconds.")
    SETTINGS.adaptiveRateLimit = Printf.enterBool(LANG.select.CHANGE_ADAPTIVE_RATE_LIMIT)
    SETTINGS.saveAsFlac = Printf.enterBool(LANG.select.CHANGE_SAVE_AS_FLAC)
    SETTINGS.saveReceipts = Printf.enterBool(LANG.select.CHANGE_SAVE_RECEIPTS)
    language = Printf.enter(LANG.select.CHANGE_LANGUAGE + "(" + LANG.getLangChoicePrint() + "):")
    # Store the numeric index like the GUI does; invalid input keeps the current language.
    if LANG.getLangName(language) and str(language).strip().isdigit():
        SETTINGS.language = int(language)
    else:
        Printf.info("Keeping existing language.")
    LANG.setLang(SETTINGS.language)
    syncPlaybackRateLimiter()
    SETTINGS.save()


def changeApiKey():
    item = apiKey.getItem(SETTINGS.apiKeyIndex)

    Printf.info(f'Current client: {SETTINGS.apiKeyIndex} {item["platform"]} ({item["formats"]})')
    Printf.apikeys(apiKey.getItems())
    index = int(Printf.enterLimit("Client index:", LANG.select.MSG_INPUT_ERR, apiKey.getLimitIndexs()))

    if index != SETTINGS.apiKeyIndex:
        SETTINGS.apiKeyIndex = index
        SETTINGS.save()
        TIDAL_API.apiKey = apiKey.getItem(index)
        TIDAL_API.logoutSavedSession()
        return True
    return False


# ------------------------------------------------------------------- login


def _displayTime(seconds, granularity=2):
    if seconds <= 0:
        return "unknown"

    result = []
    intervals = (
        ('weeks', 604800),
        ('days', 86400),
        ('hours', 3600),
        ('minutes', 60),
        ('seconds', 1),
    )

    for name, count in intervals:
        value = seconds // count
        if value:
            seconds -= value * count
            if value == 1:
                name = name.rstrip('s')
            result.append("{} {}".format(value, name))
    return ', '.join(result[:granularity])


def loginByWeb():
    try:
        print(LANG.select.AUTH_START_LOGIN)
        # get device code
        url = TIDAL_API.getDeviceCode()

        print(LANG.select.AUTH_NEXT_STEP.format(
            aigpy.cmd.green(url),
            aigpy.cmd.yellow(_displayTime(TIDAL_API.key.authCheckTimeout))))
        print(LANG.select.AUTH_WAITING)

        start = time.time()
        elapsed = 0
        while elapsed < TIDAL_API.key.authCheckTimeout:
            elapsed = time.time() - start
            if not TIDAL_API.checkAuthStatus():
                cancellable_sleep(TIDAL_API.key.authCheckInterval + 1)
                continue

            Printf.success(LANG.select.MSG_VALID_ACCESSTOKEN.format(
                _displayTime(int(TIDAL_API.key.expiresIn))))
            TIDAL_API.saveKeyToToken(TIDAL_API.keyExpiresAfter())
            return True

        raise Exception(LANG.select.AUTH_TIMEOUT)
    except DownloadCancelled:
        raise
    except Exception as e:
        Printf.err(f"Login failed: {e}")
        return False


def loginByConfig():
    try:
        if aigpy.string.isNull(TOKEN.accessToken):
            return False

        if TIDAL_API.verifyAccessToken(TOKEN.accessToken):
            Printf.info(LANG.select.MSG_VALID_ACCESSTOKEN.format(
                _displayTime(int(TOKEN.expiresAfter - time.time()))))

            TIDAL_API.key.countryCode = TOKEN.countryCode
            TIDAL_API.key.userId = TOKEN.userid
            TIDAL_API.key.accessToken = TOKEN.accessToken
            return True

        Printf.info(LANG.select.MSG_INVALID_ACCESSTOKEN)
        if not aigpy.string.isNull(TOKEN.refreshToken) and TIDAL_API.refreshAccessToken(TOKEN.refreshToken):
            Printf.success(LANG.select.MSG_VALID_ACCESSTOKEN.format(
                _displayTime(int(TIDAL_API.key.expiresIn))))
            TIDAL_API.saveKeyToToken(TIDAL_API.keyExpiresAfter())
            return True
        else:
            logout()
            return False
    except DownloadCancelled:
        raise
    except Exception as e:
        logging.warning("Unable to refresh access token: %s", e)
        return False


def logout(revoke=None):
    TIDAL_API.logoutSavedSession(revoke=revoke)
    Printf.success("Logged out.")
    return True


def loginByAccessToken():
    try:
        print("-------------AccessToken---------------")
        token = Printf.enterSecret("accessToken('0' go back):")
        if token == '0':
            return
        TIDAL_API.loginByAccessToken(token, TOKEN.userid)
    except DownloadCancelled:
        raise
    except Exception as e:
        Printf.err(str(e))
        return

    print("-------------RefreshToken---------------")
    refreshToken = Printf.enterSecret("refreshToken('0' to skip):")
    if refreshToken == '0':
        refreshToken = None

    TIDAL_API.key.refreshToken = refreshToken
    # Manually pasted tokens have no known lifetime.
    TIDAL_API.saveKeyToToken(0)
