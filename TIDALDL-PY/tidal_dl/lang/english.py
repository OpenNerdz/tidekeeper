#!/usr/bin/env python
# -*- encoding: utf-8 -*-
'''
@File    :   english.py
@Time    :   2021/11/24
@Author  :   Yaronzz & jee019
@Version :   1.2
@Contact :   yaronhuang@foxmail.com
@Desc    :   
'''

class LangEnglish(object):
    SETTING = "SETTINGS"
    VALUE = "VALUE"
    SETTING_DOWNLOAD_PATH = "Download path"
    SETTING_AUDIO_QUALITY = "Audio quality"
    SETTING_VIDEO_QUALITY = "Video quality"
    SETTING_CHECK_EXIST = "Check exist"
    SETTING_INCLUDE_EP = "Include singles & EPs"
    SETTING_SAVE_COVERS = "Save covers"
    SETTING_LANGUAGE = "Language"
    SETTING_USE_PLAYLIST_FOLDER = "Use playlist folder"
    SETTING_MULITHREAD_DOWNLOAD = "Multi thread download"
    SETTING_ALBUM_FOLDER_FORMAT = "Album folder format"
    SETTING_PLAYLIST_FOLDER_FORMAT = "Playlist folder format"
    SETTING_TRACK_FILE_FORMAT = "Track file format"
    SETTING_VIDEO_FILE_FORMAT = "Video file format"
    SETTING_SHOW_PROGRESS = "Show progress"
    SETTING_SHOW_TRACKINFO = "Show Track Info"
    SETTING_SAVE_ALBUMINFO = "Save AlbumInfo.txt"
    SETTING_DOWNLOAD_VIDEOS = "Download videos"
    SETTING_ADD_LRC_FILE = "Save timed lyrics (.lrc file)"
    SETTING_PATH = "Settings path"
    SETTING_APIKEY = "APIKey support"
    SETTING_DOWNLOAD_DELAY = "Use Download Delay"
    SETTING_REQUEST_INTERVAL_SECONDS = "Request delay seconds"
    SETTING_ADAPTIVE_RATE_LIMIT = "Automatically adapt request delay"
    SETTING_SAVE_AS_FLAC = "Save FLAC streams as .flac files"
    CHANGE_ADAPTIVE_RATE_LIMIT = "Automatically adapt request delay after HTTP 429 rate limits('0'-No,'1'-Yes):"

    PRINT_ERR = "[ERR]"
    PRINT_INFO = "[INFO]"
    PRINT_SUCCESS = "[SUCCESS]"

    PRINT_LATEST_VERSION = "Latest version:"

    CHANGE_DOWNLOAD_PATH = "Download path('0'-not modify):"
    CHANGE_AUDIO_QUALITY = "Audio quality('0'-Normal,'1'-High,'2'-HiFi,'3'-Master,'4'-Max,'5'-Atmos):"
    CHANGE_VIDEO_QUALITY = "Video quality(1080, 720, 480, 360):"
    CHANGE_CHECK_EXIST = "Check exist file before download track('0'-No,'1'-Yes):"
    CHANGE_INCLUDE_EP = "Include singles and EPs when downloading an artist's albums('0'-No,'1'-Yes):"
    CHANGE_SAVE_COVERS = "Save covers('0'-No,'1'-Yes):"
    CHANGE_LANGUAGE = "Select language"
    CHANGE_ALBUM_FOLDER_FORMAT = "Album folder format('0'-not modify,'default'-to set default):"
    CHANGE_PLAYLIST_FOLDER_FORMAT = "Playlist folder format('0'-not modify,'default'-to set default):"
    CHANGE_TRACK_FILE_FORMAT = "Track file format('0'-not modify,'default'-to set default):"
    CHANGE_VIDEO_FILE_FORMAT = "Video file format('0'-not modify,'default'-to set default):"
    CHANGE_SHOW_PROGRESS = "Show progress('0'-No,'1'-Yes):"
    CHANGE_SHOW_TRACKINFO = "Show track info('0'-No,'1'-Yes):"
    CHANGE_SAVE_ALBUM_INFO = "Save AlbumInfo.txt('0'-No,'1'-Yes):"
    CHANGE_DOWNLOAD_VIDEOS = "Download videos (when downloading playlists, albums, mixes)('0'-No,'1'-Yes):"
    CHANGE_ADD_LRC_FILE = "Save timed lyrics .lrc file ('0'-No,'1'-Yes):"
    CHANGE_MULITHREAD_DOWNLOAD = "Multi thread download('0'-No,'1'-Yes):"
    CHANGE_USE_DOWNLOAD_DELAY = "Use Download Delay('0'-No,'1'-Yes):"
    CHANGE_REQUEST_INTERVAL_SECONDS = "Request delay seconds (0=off, 30 or 60 can help rate limits):"
    CHANGE_SAVE_AS_FLAC = "Save FLAC streams as .flac files when the stream is FLAC and ffmpeg can remux it (High quality remains M4A)('0'-No,'1'-Yes):"

    # {} are required in these strings
    AUTH_START_LOGIN = "Starting login process..."
    AUTH_NEXT_STEP = "Go to {} within the next {} to complete setup."
    AUTH_WAITING = "Waiting for authorization..."
    AUTH_TIMEOUT = "Operation timed out."

    MSG_VALID_ACCESSTOKEN = "AccessToken good for {}."
    MSG_INVALID_ACCESSTOKEN = "Expired AccessToken. Attempting to refresh it."
    MSG_PATH_ERR = "Path is error!"
    MSG_INPUT_ERR = "Input error!"

    MODEL_ALBUM_PROPERTY = "ALBUM-PROPERTY"
    MODEL_TRACK_PROPERTY = "TRACK-PROPERTY"
    MODEL_VIDEO_PROPERTY = "VIDEO-PROPERTY"
    MODEL_ARTIST_PROPERTY = "ARTIST-PROPERTY"
    MODEL_PLAYLIST_PROPERTY = "PLAYLIST-PROPERTY"

    MODEL_TITLE = 'Title'
    MODEL_TRACK_NUMBER = 'Track Number'
    MODEL_VIDEO_NUMBER = 'Video Number'
    MODEL_RELEASE_DATE = 'Release Date'
    MODEL_VERSION = 'Version'
    MODEL_EXPLICIT = 'Explicit'
    MODEL_ALBUM = 'Album'
    MODEL_ID = 'ID'
    MODEL_NAME = 'Name'
    MODEL_TYPE = 'Type'
