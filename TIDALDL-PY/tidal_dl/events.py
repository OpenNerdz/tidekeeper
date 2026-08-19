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

import logging

from .download import *
from .download import __wantsAtmosDownload__  # import * skips underscore names

'''
=================================
START DOWNLOAD
=================================
'''


def __resolveAlbumForDownload__(obj: Album) -> Album:
    """Prefer the Atmos catalog twin when Atmos quality is requested."""
    if obj is None or not __wantsAtmosDownload__():
        return obj
    if TIDAL_API.__hasAtmosMode__(obj):
        return obj
    atmos = TIDAL_API.findAtmosAlbumVariant(obj)
    if atmos is None or str(getattr(atmos, "id", "")) == str(getattr(obj, "id", "")):
        return obj
    Printf.info(
        f"Using Dolby Atmos catalog release {atmos.id} "
        f"(stereo search result was {obj.id})."
    )
    return atmos


def __preferAtmosAlbums__(albums):
    """When Atmos is requested, skip stereo albums that already have an Atmos twin in the list."""
    if not albums or not __wantsAtmosDownload__():
        return albums

    atmos_titles = {
        TIDAL_API.__normalizeCatalogTitle__(getattr(album, "title", None))
        for album in albums
        if TIDAL_API.__hasAtmosMode__(album)
    }
    preferred = []
    for album in albums:
        title = TIDAL_API.__normalizeCatalogTitle__(getattr(album, "title", None))
        if (
            title
            and title in atmos_titles
            and not TIDAL_API.__hasAtmosMode__(album)
        ):
            continue
        preferred.append(album)
    return preferred


def _progress_kwargs(progress):
    return {"progress": progress} if progress is not None else {}


def start_album(obj: Album, videoOnly=False, progress=None):
    obj = __resolveAlbumForDownload__(obj)
    Printf.album(obj)
    tracks, videos = TIDAL_API.getItems(obj.id, Type.Album)
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

    albums = __preferAtmosAlbums__(TIDAL_API.getArtistAlbums(obj.id, SETTINGS.includeEP))
    Printf.artist(obj, len(albums))
    success = True
    for item in albums:
        success = start_album(item, progress=progress) and success
    return success


def start_playlist(obj: Playlist, videoOnly=False, progress=None):
    Printf.playlist(obj)
    tracks, videos = TIDAL_API.getItems(obj.uuid, Type.Playlist)
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


def start_file(string, videoOnly=False, progress=None):
    txt = aigpy.file.getContent(string)
    if aigpy.string.isNull(txt):
        Printf.err("Nothing can read!")
        return False
    array = txt.split('\n')
    success = True
    sawItem = False
    for item in array:
        if aigpy.string.isNull(item):
            continue
        if item[0] == '#':
            continue
        if item[0] == '[':
            continue
        sawItem = True
        success = start(item, videoOnly, progress=progress) and success
    return success if sawItem else False


def start_type(etype: Type, obj, videoOnly=False, progress=None):
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

    # Treat the whole input as a single token first so file paths that
    # contain spaces are not split apart.
    if os.path.exists(string.strip()):
        return start_file(string.strip(), videoOnly, progress=progress)

    strings = string.split(" ")
    success = True
    sawItem = False
    for item in strings:
        if aigpy.string.isNull(item):
            continue
        if os.path.exists(item):
            return start_file(item, videoOnly, progress=progress)

        sawItem = True
        try:
            etype, obj = TIDAL_API.getByString(item)
        except Exception as e:
            Printf.err(str(e) + " [" + item + "]")
            return False

        try:
            if not start_type(etype, obj, videoOnly, progress=progress):
                success = False
        except Exception as e:
            Printf.err(str(e))
            success = False
    return success if sawItem else False


'''
=================================
CHANGE SETTINGS
=================================
'''


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
    SETTINGS.audioQuality = AudioQuality(
        int(Printf.enterLimit(LANG.select.CHANGE_AUDIO_QUALITY,
                              LANG.select.MSG_INPUT_ERR,
                              ['0', '1', '2', '3', '4', '5'])))
    priority = Printf.enter(
        "Audio quality priority comma list, blank for single quality, e.g. Atmos,High,Lossless,Low:"
    )
    SETTINGS.audioQualityPriority = SETTINGS.getAudioQualityPriority(priority)
    if SETTINGS.audioQualityPriority:
        SETTINGS.audioQuality = SETTINGS.audioQualityPriority[0]
    SETTINGS.videoQuality = VideoQuality(
        int(Printf.enterLimit(LANG.select.CHANGE_VIDEO_QUALITY,
                              LANG.select.MSG_INPUT_ERR,
                              ['1080', '720', '480', '360'])))
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
    SETTINGS.usePlaylistFolder = Printf.enterBool(LANG.select.SETTING_USE_PLAYLIST_FOLDER + "('0'-No,'1'-Yes):")
    SETTINGS.downloadDelay = Printf.enterBool(LANG.select.CHANGE_USE_DOWNLOAD_DELAY)
    interval_prompt = getattr(
        LANG.select,
        "CHANGE_REQUEST_INTERVAL_SECONDS",
        "Request delay seconds (0=off, 30 or 60 can help rate limits):",
    )
    interval = Printf.enter(interval_prompt)
    try:
        SETTINGS.requestIntervalSeconds = max(0.0, float(interval))
    except (TypeError, ValueError):
        Printf.info("Keeping existing request delay seconds.")
    SETTINGS.adaptiveRateLimit = Printf.enterBool(getattr(
        LANG.select,
        "CHANGE_ADAPTIVE_RATE_LIMIT",
        "Automatically adapt request delay after HTTP 429 rate limits('0'-No,'1'-Yes):",
    ))
    SETTINGS.saveAsFlac = Printf.enterBool(getattr(
        LANG.select,
        "CHANGE_SAVE_AS_FLAC",
        "Save FLAC streams as .flac files when the stream is FLAC and ffmpeg can remux it (High quality remains M4A)('0'-No,'1'-Yes):",
    ))
    SETTINGS.language = Printf.enter(LANG.select.CHANGE_LANGUAGE + "(" + LANG.getLangChoicePrint() + "):")
    LANG.setLang(SETTINGS.language)
    syncPlaybackRateLimiter()
    SETTINGS.save()


def changeApiKey():
    item = apiKey.getItem(SETTINGS.apiKeyIndex)
    ver = apiKey.getVersion()

    Printf.info(f'Current APIKeys: {str(SETTINGS.apiKeyIndex)} {item["platform"]}-{item["formats"]}')
    Printf.info(f'Current Version: {str(ver)}')
    Printf.apikeys(apiKey.getItems())
    index = int(Printf.enterLimit("APIKEY index:", LANG.select.MSG_INPUT_ERR, apiKey.getLimitIndexs()))

    if index != SETTINGS.apiKeyIndex:
        SETTINGS.apiKeyIndex = index
        SETTINGS.save()
        TIDAL_API.apiKey = apiKey.getItem(index)
        return True
    return False


'''
=================================
LOGIN
=================================
'''


def __displayTime__(seconds, granularity=2):
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
            aigpy.cmd.yellow(__displayTime__(TIDAL_API.key.authCheckTimeout))))
        print(LANG.select.AUTH_WAITING)

        start = time.time()
        elapsed = 0
        while elapsed < TIDAL_API.key.authCheckTimeout:
            elapsed = time.time() - start
            if not TIDAL_API.checkAuthStatus():
                time.sleep(TIDAL_API.key.authCheckInterval + 1)
                continue

            Printf.success(LANG.select.MSG_VALID_ACCESSTOKEN.format(
                __displayTime__(int(TIDAL_API.key.expiresIn))))

            TOKEN.userid = TIDAL_API.key.userId
            TOKEN.countryCode = TIDAL_API.key.countryCode
            TOKEN.accessToken = TIDAL_API.key.accessToken
            TOKEN.refreshToken = TIDAL_API.key.refreshToken
            TOKEN.expiresAfter = time.time() + int(TIDAL_API.key.expiresIn)
            TOKEN.save()
            return True

        raise Exception(LANG.select.AUTH_TIMEOUT)
    except Exception as e:
        Printf.err(f"Login failed.{str(e)}")
        return False


def loginByConfig():
    try:
        if aigpy.string.isNull(TOKEN.accessToken):
            return False

        if TIDAL_API.verifyAccessToken(TOKEN.accessToken):
            Printf.info(LANG.select.MSG_VALID_ACCESSTOKEN.format(
                __displayTime__(int(TOKEN.expiresAfter - time.time()))))

            TIDAL_API.key.countryCode = TOKEN.countryCode
            TIDAL_API.key.userId = TOKEN.userid
            TIDAL_API.key.accessToken = TOKEN.accessToken
            return True

        Printf.info(LANG.select.MSG_INVALID_ACCESSTOKEN)
        if not aigpy.string.isNull(TOKEN.refreshToken) and TIDAL_API.refreshAccessToken(TOKEN.refreshToken):
            Printf.success(LANG.select.MSG_VALID_ACCESSTOKEN.format(
                __displayTime__(int(TIDAL_API.key.expiresIn))))

            TOKEN.userid = TIDAL_API.key.userId
            TOKEN.countryCode = TIDAL_API.key.countryCode
            TOKEN.accessToken = TIDAL_API.key.accessToken
            TOKEN.refreshToken = TIDAL_API.key.refreshToken
            TOKEN.expiresAfter = time.time() + int(TIDAL_API.key.expiresIn)
            TOKEN.save()
            return True
        else:
            logout()
            return False
    except Exception as e:
        logging.warning("Unable to refresh access token: %s", e)
        return False


def logout():
    TOKEN.userid = None
    TOKEN.countryCode = None
    TOKEN.accessToken = None
    TOKEN.refreshToken = None
    TOKEN.expiresAfter = 0
    TOKEN.save()

    TIDAL_API.key.userId = None
    TIDAL_API.key.countryCode = None
    TIDAL_API.key.accessToken = None
    TIDAL_API.key.refreshToken = None
    TIDAL_API.key.expiresIn = None
    TIDAL_API._atmosUnavailableTrackIds.clear()
    Printf.success("Logged out.")
    return True


def loginByAccessToken():
    try:
        print("-------------AccessToken---------------")
        token = Printf.enter("accessToken('0' go back):")
        if token == '0':
            return
        TIDAL_API.loginByAccessToken(token, TOKEN.userid)
    except Exception as e:
        Printf.err(str(e))
        return

    print("-------------RefreshToken---------------")
    refreshToken = Printf.enter("refreshToken('0' to skip):")
    if refreshToken == '0':
        refreshToken = TOKEN.refreshToken

    TOKEN.accessToken = token
    TOKEN.refreshToken = refreshToken
    TOKEN.userid = TIDAL_API.key.userId
    TOKEN.expiresAfter = 0
    TOKEN.countryCode = TIDAL_API.key.countryCode
    TOKEN.save()
