#!/usr/bin/env python
# -*- encoding: utf-8 -*-
'''
@File    :   japanese.py
@Time    :   2021/11/30
@Author  :   jee019
@Version :   1.0
@Contact :   qwer010910@gmail.com
@Desc    :
'''

class LangJapanese(object):
    SETTING = "設定"
    VALUE = "値"
    SETTING_DOWNLOAD_PATH = "ダウンロードパス"
    SETTING_AUDIO_QUALITY = "オーディオ品質"
    SETTING_VIDEO_QUALITY = "ビデオ品質"
    SETTING_CHECK_EXIST = "Check exist"
    SETTING_INCLUDE_EP = "含む singles & EPs"
    SETTING_SAVE_COVERS = "カバーを保存"
    SETTING_LANGUAGE = "言語"
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
    SETTING_PATH = "設定パス"
    SETTING_APIKEY = "APIKey support"
    SETTING_DOWNLOAD_DELAY = "Use Download Delay"

    PRINT_ERR = "[エラー]"
    PRINT_INFO = "[情報]"
    PRINT_SUCCESS = "[サクセス]"

    PRINT_LATEST_VERSION = "最新バージョン:"

    CHANGE_DOWNLOAD_PATH = "ダウンロードパス('0'-変更しない):"
    CHANGE_AUDIO_QUALITY = "オーディオ品質('0'-Normal,'1'-High,'2'-HiFi,'3'-Master,'4'-Max):"
    CHANGE_VIDEO_QUALITY = "ビデオ品質(1080, 720, 480, 360):"
    CHANGE_CHECK_EXIST = "Check exist file before download track('0'-いいえ,'1'-はい):"
    CHANGE_INCLUDE_EP = "Include singles and EPs when downloading an artist's albums('0'-いいえ,'1'-はい):"
    CHANGE_SAVE_COVERS = "カバーを保存('0'-いいえ,'1'-はい):"
    CHANGE_LANGUAGE = "言語を選択する"
    CHANGE_ALBUM_FOLDER_FORMAT = "Album folder format('0'-変更しない,'default'-デフォルトを設定するには):"
    CHANGE_PLAYLIST_FOLDER_FORMAT = "Playlist folder format('0'-not modify,'default'-to set default):"
    CHANGE_TRACK_FILE_FORMAT = "Track file format('0'-変更しない,'default'-デフォルトを設定するには):"
    CHANGE_VIDEO_FILE_FORMAT = "Video file format('0'-not modify,'default'-to set default):"
    CHANGE_SHOW_PROGRESS = "Show progress('0'-いいえ,'1'-はい):"
    CHANGE_SHOW_TRACKINFO = "Show track info('0'-いいえ,'1'-はい):"
    CHANGE_SAVE_ALBUM_INFO = "Save AlbumInfo.txt('0'-いいえ,'1'-はい):"
    CHANGE_DOWNLOAD_VIDEOS = "Download videos (when downloading playlists, albums, mixes)('0'-No,'1'-Yes):"
    CHANGE_ADD_LRC_FILE = "Save timed lyrics .lrc file ('0'-いいえ,'1'-はい):"
    CHANGE_MULITHREAD_DOWNLOAD = "Multi thread download('0'-No,'1'-Yes):"
    CHANGE_USE_DOWNLOAD_DELAY = "Use Download Delay('0'-No,'1'-Yes):"

    # {} are required in these strings
    AUTH_START_LOGIN = "Starting login process..."
    AUTH_NEXT_STEP = "Go to {} within the next {} to complete setup."
    AUTH_WAITING = "Waiting for authorization..."
    AUTH_TIMEOUT = "Operation timed out."

    MSG_VALID_ACCESSTOKEN = "AccessToken good for {}."
    MSG_INVALID_ACCESSTOKEN = "Expired AccessToken. Attempting to refresh it."
    MSG_PATH_ERR = "パスはエラーです!"
    MSG_INPUT_ERR = "入力エラー!"

    MODEL_ALBUM_PROPERTY = "アルバム-情報"
    MODEL_TRACK_PROPERTY = "トラック-情報"
    MODEL_VIDEO_PROPERTY = "ビデオ-情報"
    MODEL_ARTIST_PROPERTY = "アーティスト-情報"
    MODEL_PLAYLIST_PROPERTY = "プレイリスト-情報"

    MODEL_TITLE = '題名'
    MODEL_TRACK_NUMBER = 'トラック番号'
    MODEL_VIDEO_NUMBER = 'ビデオ番号'
    MODEL_RELEASE_DATE = '発売日'
    MODEL_VERSION = 'バージョン'
    MODEL_EXPLICIT = 'Explicit'
    MODEL_ALBUM = 'アルバム'
    MODEL_ID = 'ID'
    MODEL_NAME = '名前'
    MODEL_TYPE = 'タイプ'
