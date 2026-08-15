#!/usr/bin/env python
# -*- encoding: utf-8 -*-
'''
@File    :   filipino.py
@Time    :   2020/08/21
@Author  :   Ni Ño
@Version :   1.0
@Contact :
@Desc    :
'''

class LangFilipino(object):
    SETTING = "SETTINGS"
    VALUE = "VALUE"
    SETTING_DOWNLOAD_PATH = "Paroroonan ng Download"
    SETTING_AUDIO_QUALITY = "Kalidad ng Audio"
    SETTING_VIDEO_QUALITY = "Kalidad ng Video"
    SETTING_CHECK_EXIST = "Suriin kung mayroon na"
    SETTING_INCLUDE_EP = "Isama ang single at ep"
    SETTING_SAVE_COVERS = "I-save ang mga cover"
    SETTING_LANGUAGE = "Lenggwahe"
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

    PRINT_ERR = "[ERR]"
    PRINT_INFO = "[INFO]"
    PRINT_SUCCESS = "[TAPOS NA]"

    PRINT_LATEST_VERSION = "Pinakabagong Version:"

    CHANGE_DOWNLOAD_PATH = "Paroroonan ng Download('0' walang babaguhin):"
    CHANGE_AUDIO_QUALITY = "Kalidad ng Audio('0'-Normal,'1'-High,'2'-HiFi,'3'-Master,'4'-Max):"
    CHANGE_VIDEO_QUALITY = "Kalidad ng Audio Video(1080, 720, 480, 360):"
    CHANGE_CHECK_EXIST = "Suriin kung naidownload na bago mag download muli('0'-Hindi,'1'-Oo):"
    CHANGE_INCLUDE_EP = "Isama ang singles at EPs sa pagdownload ng mga album mula sa artist('0'-Hindi,'1'-Oo):"
    CHANGE_SAVE_COVERS = "I-save ang mga covers('0'-Hindi,'1'-Oo):"
    CHANGE_LANGUAGE = "Pumili ng lenggwahe"
    CHANGE_ALBUM_FOLDER_FORMAT = "Album folder format('0' not modify,'default'-to set default):"
    CHANGE_PLAYLIST_FOLDER_FORMAT = "Playlist folder format('0'-not modify,'default'-to set default):"
    CHANGE_TRACK_FILE_FORMAT = "Track file format('0' not modify,'default'-to set default):"
    CHANGE_VIDEO_FILE_FORMAT = "Video file format('0'-not modify,'default'-to set default):"
    CHANGE_SHOW_PROGRESS = "Show progress('0'-No,'1'-Yes):"
    CHANGE_SHOW_TRACKINFO = "Show track info('0'-No,'1'-Yes):"
    CHANGE_SAVE_ALBUM_INFO = "Save AlbumInfo.txt('0'-No,'1'-Yes):"
    CHANGE_DOWNLOAD_VIDEOS = "Download videos (when downloading playlists, albums, mixes)('0'-No,'1'-Yes):"
    CHANGE_ADD_LRC_FILE = "Save timed lyrics .lrc file ('0'-No,'1'-Yes):"
    CHANGE_MULITHREAD_DOWNLOAD = "Multi thread download('0'-No,'1'-Yes):"
    CHANGE_USE_DOWNLOAD_DELAY = "Use Download Delay('0'-No,'1'-Yes):"

    # {} are required in these strings
    AUTH_START_LOGIN = "Starting login process..."
    AUTH_NEXT_STEP = "Go to {} within the next {} to complete setup."
    AUTH_WAITING = "Waiting for authorization..."
    AUTH_TIMEOUT = "Operation timed out."

    MSG_VALID_ACCESSTOKEN = "AccessToken good for {}."
    MSG_INVALID_ACCESSTOKEN = "Expired AccessToken. Attempting to refresh it."
    MSG_PATH_ERR = "May error sa paroroonan ng download!"
    MSG_INPUT_ERR = "May error sa pag-input!"

    MODEL_ALBUM_PROPERTY = "PROPERTY NG ALBUM"
    MODEL_TRACK_PROPERTY = "PROPERTY NG TRACK"
    MODEL_VIDEO_PROPERTY = "PROPERTY NG VIDEO"
    MODEL_ARTIST_PROPERTY = "PROPERTY NG ARTIST"
    MODEL_PLAYLIST_PROPERTY = "PROPERTY NG PLAYLIST"

    MODEL_TITLE = 'Pamagat'
    MODEL_TRACK_NUMBER = 'Bilang ng Track'
    MODEL_VIDEO_NUMBER = 'Bilang ng Video'
    MODEL_RELEASE_DATE = 'Petsa ng Pag-release'
    MODEL_VERSION = 'Bersyon'
    MODEL_EXPLICIT = 'Explicit'
    MODEL_ALBUM = 'Album'
    MODEL_ID = 'ID'
    MODEL_NAME = 'Pangalan'
    MODEL_TYPE = 'Uri'
