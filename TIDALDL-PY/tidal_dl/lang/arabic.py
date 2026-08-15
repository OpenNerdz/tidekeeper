#!/usr/bin/env python
# -*- encoding: utf-8 -*-
'''
@File    :   arabic.py
@Time    :   2020/08/19
@Author  :   shhade for hack
@Version :   1.0
@Contact :
@Desc    :
'''

class LangArabic(object):
    SETTING = "الاعدادت"
    VALUE = "القيمة"
    SETTING_DOWNLOAD_PATH = "مجلد التحميل"
    SETTING_AUDIO_QUALITY = "دقة الصوت"
    SETTING_VIDEO_QUALITY = "دقة الفديو"
    SETTING_CHECK_EXIST = "التاكد من وجود الملف قبل التنزيل"
    SETTING_INCLUDE_EP = "اضافة single&ep"
    SETTING_SAVE_COVERS = "حفظ صورة الالبوم"
    SETTING_LANGUAGE = "اللغة"
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
    SETTING_PATH = "Settings path"
    SETTING_ADD_LRC_FILE = "Save timed lyrics (.lrc file)"
    SETTING_APIKEY = "APIKey support"
    SETTING_DOWNLOAD_DELAY = "Use Download Delay"

    PRINT_ERR = "[خطأ]"
    PRINT_INFO = "[معلومة]"
    PRINT_SUCCESS = "[نجاح]"

    PRINT_LATEST_VERSION = "آخر اصدر:"

    CHANGE_DOWNLOAD_PATH = "مجلد التنزيل('0' not modify):"
    CHANGE_AUDIO_QUALITY = "دقة الصوت('0'-Normal,'1'-High,'2'-HiFi,'3'-Master,'4'-Max):"
    CHANGE_VIDEO_QUALITY = "دقة الفديو(1080, 720, 480, 360):"
    CHANGE_CHECK_EXIST = "التحقق من وجود الملف قبل التحميل('0'-No,'1'-Yes):"
    CHANGE_INCLUDE_EP = "اضافة مسطلحات فردي او ثنائي الى الغنية('0'-No,'1'-Yes):"
    CHANGE_SAVE_COVERS = "حفظ صورة الالبوم('0'-No,'1'-Yes):"
    CHANGE_LANGUAGE = "اختر لغة"
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

    # {} are required in these strings
    AUTH_START_LOGIN = "Starting login process..."
    AUTH_NEXT_STEP = "Go to {} within the next {} to complete setup."
    AUTH_WAITING = "Waiting for authorization..."
    AUTH_TIMEOUT = "Operation timed out."

    MSG_VALID_ACCESSTOKEN = "AccessToken good for {}."
    MSG_INVALID_ACCESSTOKEN = "Expired AccessToken. Attempting to refresh it."
    MSG_PATH_ERR = "!مجلد التنزيل خاطئ"
    MSG_INPUT_ERR = "!ادخال خاطئ"

    MODEL_ALBUM_PROPERTY = "ملكية الالبوم"
    MODEL_TRACK_PROPERTY = "ملكية الاغنية"
    MODEL_VIDEO_PROPERTY = "ملكية الفديو"
    MODEL_ARTIST_PROPERTY = "ملكية الفنان"
    MODEL_PLAYLIST_PROPERTY = "ملكية قائمة الاغاني"

    MODEL_TITLE = 'الاسم'
    MODEL_TRACK_NUMBER = 'رقم الاغنية'
    MODEL_VIDEO_NUMBER = 'رقم الفديو'
    MODEL_RELEASE_DATE = 'عام الاصدار'
    MODEL_VERSION = 'الاصدار'
    MODEL_EXPLICIT = 'توقيع الفنان'
    MODEL_ALBUM = 'الالبوم'
    MODEL_ID = 'رقم التتبع'
    MODEL_NAME = 'الاسم'
    MODEL_TYPE = 'النوع'
