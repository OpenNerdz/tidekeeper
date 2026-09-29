#!/usr/bin/env python
# -*- encoding: utf-8 -*-
'''
@File    :   printf.py
@Time    :   2020/08/16
@Author  :   Yaronzz
@Version :   3.0
@Contact :   yaronhuang@foxmail.com
@Desc    :
'''
import threading
import aigpy
from .runtime import print
import logging
import requests
import prettytable
import shutil
import getpass

from . import apiKey

from .enums import AUDIO_QUALITY_ORDER, Type, VideoQuality
from .model import Album, Artist, StreamUrl, Track, Video, VideoStreamUrl
from .paths import PATHS
from .settings import SETTINGS, TOKEN
from .tidal import TIDAL_API
from .environment import isTermux
from .lang.language import LANG


VERSION = '2026.9.29.3'
PROJECT_URL = 'https://github.com/OpenNerdz/tidekeeper'

print_mutex = threading.Lock()


class Printf(object):

    @staticmethod
    def logo():
        text = f"Tidekeeper {VERSION}\n{PROJECT_URL}"
        print(text)
        logging.info(text)

    @staticmethod
    def clearScreen():
        print("\033[2J\033[H", end="")

    @staticmethod
    def _enumName(value):
        text = str(value)
        return text.rsplit(".", 1)[-1]

    @staticmethod
    def _shorten(value, width=68):
        value = str(value)
        if len(value) <= width:
            return value
        return value[:width - 3] + "..."

    @staticmethod
    def _terminalWidth():
        return shutil.get_terminal_size((80, 20)).columns

    @staticmethod
    def _isCompact():
        return isTermux() or Printf._terminalWidth() < 72

    @staticmethod
    def _gettable(columns, rows):
        tb = prettytable.PrettyTable()
        tb.field_names = list(aigpy.cmd.green(item) for item in columns)
        tb.align = 'l'
        for item in rows:
            tb.add_row(item)
        return tb

    @staticmethod
    def usage():
        Printf.logo()
        print("")
        qualities = ", ".join(item.name for item in AUDIO_QUALITY_ORDER)
        resolutions = ", ".join(item.name for item in reversed(VideoQuality))
        rows = [
            ("-h, --help", "Show help"),
            ("-v, --version", "Show version"),
            ("-g, --gui", "Open GUI if available"),
            ("--update", "Update terminal install"),
            ("--update-gui", "Update terminal and GUI install"),
            ("--doctor", "Check config, auth, and local tools"),
            ("--paths", "Show download/config paths"),
            ("--open-output", "Open download folder"),
            ("--migrate-downloads PATH", "Merge a literal-~ folder from older releases"),
            ("--video-only", "Download videos only for URL/ID/file"),
            ("-l, --link URL", "Download URL/ID/file"),
            ("-o, --output PATH", "Set save folder"),
            ("-q, --quality NAME", f"{qualities} (default: Max; legacy Master accepted)"),
            ("--quality-priority LIST", "Fallback order, e.g. Max,HiFi,High,Normal"),
            ("-r, --resolution NAME", resolutions),
            ("-c, --configPathOverride PATH", "Use non-default base path for config/tokens/logs"),
        ]
        if Printf._isCompact():
            for option, description in rows:
                print(option)
                print(f"  {description}")
            return

        tb = Printf._gettable(["OPTION", "DESCRIPTION"], rows)
        tb.set_style(prettytable.TableStyle.PLAIN_COLUMNS)
        print(tb)

    @staticmethod
    def paths():
        tb = Printf._gettable(["PATH", "VALUE"], PATHS.getPathSummary())
        tb.set_style(prettytable.TableStyle.PLAIN_COLUMNS)
        print(tb)

    @staticmethod
    def checkVersion():
        try:
            with requests.get('https://pypi.org/pypi/tidekeeper/json', timeout=(3, 5)) as response:
                response.raise_for_status()
                onlineVer = response.json()['info']['version']
            if aigpy.system.cmpVersion(onlineVer, VERSION) > 0:
                Printf.info(LANG.select.PRINT_LATEST_VERSION + ' ' + onlineVer)
        except (requests.RequestException, KeyError, TypeError, ValueError):
            logging.debug('Version check unavailable')

    @staticmethod
    def settings():
        data = SETTINGS
        configuredPriority = data.getAudioQualityPriority(data.audioQualityPriority)
        qualityPriority = ",".join(
            item.name for item in (data.getDownloadAudioQualityPriority() if configuredPriority else [])
        ) or "off"

        tb = Printf._gettable([LANG.select.SETTING, LANG.select.VALUE], [
            # Paths and naming
            [LANG.select.SETTING_PATH, PATHS.getProfilePath()],
            [LANG.select.SETTING_DOWNLOAD_PATH, data.downloadPath],
            [LANG.select.SETTING_ALBUM_FOLDER_FORMAT, data.albumFolderFormat],
            [LANG.select.SETTING_PLAYLIST_FOLDER_FORMAT, data.playlistFolderFormat],
            [LANG.select.SETTING_TRACK_FILE_FORMAT, data.trackFileFormat],
            [LANG.select.SETTING_VIDEO_FILE_FORMAT, data.videoFileFormat],

            # Quality
            [LANG.select.SETTING_AUDIO_QUALITY, data.audioQuality],
            ["Audio quality priority", qualityPriority],
            [LANG.select.SETTING_VIDEO_QUALITY, data.videoQuality],

            # Options
            [LANG.select.SETTING_USE_PLAYLIST_FOLDER, data.usePlaylistFolder],
            [LANG.select.SETTING_CHECK_EXIST, data.checkExist],
            [LANG.select.SETTING_SHOW_PROGRESS, data.showProgress],
            [LANG.select.SETTING_SHOW_TRACKINFO, data.showTrackInfo],
            [LANG.select.SETTING_SAVE_ALBUMINFO, data.saveAlbumInfo],
            [LANG.select.SETTING_DOWNLOAD_VIDEOS, data.downloadVideos],
            [LANG.select.SETTING_SAVE_COVERS, data.saveCovers],
            [LANG.select.SETTING_INCLUDE_EP, data.includeEP],
            [LANG.select.SETTING_LANGUAGE, LANG.getLangName(data.language)],
            [LANG.select.SETTING_ADD_LRC_FILE, data.lyricFile],
            [LANG.select.SETTING_MULITHREAD_DOWNLOAD, data.multiThread],
            ["Concurrent tracks", data.concurrentTracks],
            ["Segments per track", data.segmentsPerTrack],
            [LANG.select.SETTING_APIKEY, f"[{data.apiKeyIndex}]" + apiKey.getItem(data.apiKeyIndex)['formats']],
            [LANG.select.SETTING_DOWNLOAD_DELAY, data.downloadDelay],
            [LANG.select.SETTING_REQUEST_INTERVAL_SECONDS, data.requestIntervalSeconds],
            [LANG.select.SETTING_ADAPTIVE_RATE_LIMIT, data.adaptiveRateLimit],
            [LANG.select.SETTING_SAVE_AS_FLAC, data.saveAsFlac],
        ])
        print(tb)

    @staticmethod
    def dashboard():
        data = SETTINGS
        signed_in = not aigpy.string.isNull(TOKEN.accessToken)
        account = aigpy.cmd.green("signed in") if signed_in else aigpy.cmd.yellow("not signed in")
        region = TOKEN.countryCode or "unknown"
        compact = Printf._isCompact()
        path = Printf._shorten(data.downloadPath, 42 if compact else 68)
        audio = Printf._enumName(data.audioQuality)
        priority = data.getDownloadAudioQualityPriority()
        if priority:
            audio = ">".join(item.name for item in priority)
        video = Printf._enumName(data.videoQuality)

        print("")
        print(aigpy.cmd.green(f"Tidekeeper {VERSION}"))
        print(f"Account: {account} ({region})")
        print(f"Quality: audio {audio}, video {video}")
        print(f"Save to: {path}")
        print("")
        print(aigpy.cmd.green("Download: paste a TIDAL URL, ID, or list file and press Enter."))
        print("")
        if compact:
            print("1 Login / refresh")
            print("2 Logout")
            print("3 Set token")
            print("4 Save folder")
            print("5 Quality")
            print("6 Options")
            print("7 Client")
            print("8 Full settings")
            print("9 Update")
            print("0 Exit")
            print("clear / cls Clear screen")
        else:
            print("1 Login/refresh   2 Logout        3 Set token")
            print("4 Save folder     5 Quality       6 Options")
            print("7 Client          8 Full settings 9 Update")
            print("0 Exit")
            print("clear/cls Clear screen")
        print("")

    @staticmethod
    def choices():
        Printf.dashboard()

    @staticmethod
    def enter(string):
        aigpy.cmd.colorPrint(string, aigpy.cmd.TextColor.Yellow, None)
        return input("")

    @staticmethod
    def enterSecret(string):
        return getpass.getpass(string + ' ')

    @staticmethod
    def enterBool(string):
        return Printf.enter(string) == '1'

    @staticmethod
    def enterPath(string, errmsg, retWord='0', default=""):
        while True:
            ret = aigpy.cmd.inputPath(aigpy.cmd.yellow(string), retWord)
            if ret == retWord:
                return default
            elif ret == "":
                print(aigpy.cmd.red(LANG.select.PRINT_ERR + " ") + errmsg)
            else:
                break
        return ret

    @staticmethod
    def enterLimit(string, errmsg, limit=None):
        if limit is None:
            limit = []
        while True:
            ret = aigpy.cmd.inputLimit(aigpy.cmd.yellow(string), limit)
            if ret is None:
                print(aigpy.cmd.red(LANG.select.PRINT_ERR + " ") + errmsg)
            else:
                break
        return ret

    @staticmethod
    def enterFormat(string, current, default):
        ret = Printf.enter(string)
        if ret == '0' or aigpy.string.isNull(ret):
            return current
        if ret.lower() == 'default':
            return default
        return ret

    # A failed write (closed pipe, unencodable console text) must never leave
    # the mutex held, or every later message from every worker would block.
    @staticmethod
    def err(string):
        with print_mutex:
            print(aigpy.cmd.red(LANG.select.PRINT_ERR + " ") + string)
        logging.info("Error: %s", string)

    @staticmethod
    def info(string):
        with print_mutex:
            print(aigpy.cmd.blue(LANG.select.PRINT_INFO + " ") + string)

    @staticmethod
    def success(string):
        with print_mutex:
            print(aigpy.cmd.green(LANG.select.PRINT_SUCCESS + " ") + string)

    @staticmethod
    def album(data: Album):
        modes = getattr(data, "audioModes", None) or []
        modes_label = ", ".join(str(mode) for mode in modes) if modes else ""
        flag = TIDAL_API.getFlag(data, Type.Album, short=False)
        tb = Printf._gettable([LANG.select.MODEL_ALBUM_PROPERTY, LANG.select.VALUE], [
            [LANG.select.MODEL_TITLE, data.title],
            ["ID", data.id],
            [LANG.select.MODEL_TRACK_NUMBER, data.numberOfTracks],
            [LANG.select.MODEL_VIDEO_NUMBER, data.numberOfVideos],
            [LANG.select.MODEL_RELEASE_DATE, data.releaseDate],
            [LANG.select.MODEL_VERSION, data.version],
            [LANG.select.MODEL_EXPLICIT, data.explicit],
            ["Max-Q", getattr(data, "audioQuality", None)],
            ["Audio modes", modes_label or None],
            ["Flags", flag or None],
        ])
        print(tb)
        logging.info("Album %s: title=%s tracks=%s videos=%s",
                     data.id, data.title, data.numberOfTracks, data.numberOfVideos)

    @staticmethod
    def track(data: Track, stream: StreamUrl = None):
        tb = Printf._gettable([LANG.select.MODEL_TRACK_PROPERTY, LANG.select.VALUE], [
            [LANG.select.MODEL_TITLE, data.title],
            ["ID", data.id],
            [LANG.select.MODEL_ALBUM, data.album.title],
            [LANG.select.MODEL_VERSION, data.version],
            [LANG.select.MODEL_EXPLICIT, data.explicit],
            ["Max-Q", data.audioQuality],
        ])
        if stream is not None:
            tb.add_row(["Get-Q", str(stream.soundQuality)])
            tb.add_row(["Get-Codec", str(stream.codec)])
            bit_depth = getattr(stream, 'bitDepth', None)
            sample_rate = getattr(stream, 'sampleRate', None)
            if bit_depth or sample_rate:
                depth = f"{bit_depth}-bit" if bit_depth else "unknown depth"
                rate = f"{int(sample_rate) / 1000:g} kHz" if sample_rate else "unknown rate"
                tb.add_row(["Actual format", f"{depth} / {rate}"])
            if stream.fallbackReason:
                tb.add_row(["Requested-Q", str(stream.requestedQuality)])
                tb.add_row(["Fallback", f"{stream.fallbackQuality} ({stream.fallbackReason})"])
        print(tb)
        logging.info("Track %s: title=%s version=%s quality=%s fallback=%s",
                     data.id, data.title, data.version,
                     getattr(stream, 'soundQuality', ''), getattr(stream, 'fallbackError', ''))

    @staticmethod
    def video(data: Video, stream: VideoStreamUrl = None):
        tb = Printf._gettable([LANG.select.MODEL_VIDEO_PROPERTY, LANG.select.VALUE], [
            [LANG.select.MODEL_TITLE, data.title],
            [LANG.select.MODEL_ALBUM, data.album.title if data.album is not None else None],
            [LANG.select.MODEL_VERSION, data.version],
            [LANG.select.MODEL_EXPLICIT, data.explicit],
            ["Max-Q", data.quality],
        ])
        if stream is not None:
            tb.add_row(["Get-Q", str(stream.resolution)])
            tb.add_row(["Get-Codec", str(stream.codec)])
        print(tb)
        logging.info("Video %s: title=%s version=%s", data.id, data.title, data.version)

    @staticmethod
    def artist(data: Artist, num, countLabel="Number of albums"):
        tb = Printf._gettable([LANG.select.MODEL_ARTIST_PROPERTY, LANG.select.VALUE], [
            [LANG.select.MODEL_ID, data.id],
            [LANG.select.MODEL_NAME, data.name],
            [countLabel, num],
            [LANG.select.MODEL_TYPE, str(data.type)],
        ])
        print(tb)
        logging.info("Artist %s: name=%s %s=%s", data.id, data.name, countLabel.lower(), num)

    @staticmethod
    def playlist(data):
        tb = Printf._gettable([LANG.select.MODEL_PLAYLIST_PROPERTY, LANG.select.VALUE], [
            [LANG.select.MODEL_TITLE, data.title],
            [LANG.select.MODEL_TRACK_NUMBER, data.numberOfTracks],
            [LANG.select.MODEL_VIDEO_NUMBER, data.numberOfVideos],
        ])
        print(tb)
        logging.info("Playlist %s: title=%s tracks=%s videos=%s",
                     data.uuid, data.title, data.numberOfTracks, data.numberOfVideos)

    @staticmethod
    def mix(data):
        tb = Printf._gettable([LANG.select.MODEL_PLAYLIST_PROPERTY, LANG.select.VALUE], [
            [LANG.select.MODEL_ID, data.id],
            [LANG.select.MODEL_TRACK_NUMBER, len(data.tracks)],
            [LANG.select.MODEL_VIDEO_NUMBER, len(data.videos)],
        ])
        print(tb)
        logging.info("Mix %s: tracks=%s videos=%s", data.id, len(data.tracks), len(data.videos))

    @staticmethod
    def apikeys(items):
        print("TIDAL clients")
        if Printf._isCompact():
            for item in items:
                print(f"{item['index']} - {item['platform']}")
                print(f"  {item['formats']}")
            return

        tb = Printf._gettable(["Index", "Platform", "Formats"], [
            [item["index"], item["platform"], item["formats"]] for item in items
        ])
        print(tb)
