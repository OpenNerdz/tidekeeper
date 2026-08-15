#!/usr/bin/env python
# -*- encoding: utf-8 -*-
'''
@File    :   chinese.py
@Time    :   2020/08/19
@Author  :   Yaronzz
@Version :   1.0
@Contact :   yaronhuang@foxmail.com
@Desc    :
'''

class LangChinese(object):
    SETTING = "设置"
    VALUE = "值"
    SETTING_DOWNLOAD_PATH = "下载目录"
    SETTING_AUDIO_QUALITY = "歌曲质量"
    SETTING_VIDEO_QUALITY = "视频质量"
    SETTING_CHECK_EXIST = "是否跳过已下载的文件"
    SETTING_INCLUDE_EP = "下载歌手专辑时包含其EP单曲"
    SETTING_SAVE_COVERS = "保存封面"
    SETTING_LANGUAGE = "语言"
    SETTING_USE_PLAYLIST_FOLDER = "将歌单下载到歌单目录"
    SETTING_MULITHREAD_DOWNLOAD = "多线程下载"
    SETTING_ALBUM_FOLDER_FORMAT = "专辑目录格式"
    SETTING_PLAYLIST_FOLDER_FORMAT = "Playlist folder format"
    SETTING_TRACK_FILE_FORMAT = "歌曲文件名格式"
    SETTING_VIDEO_FILE_FORMAT = "视频文件格式"
    SETTING_SHOW_PROGRESS = "显示进度条"
    SETTING_SHOW_TRACKINFO = "显示歌曲信息"
    SETTING_SAVE_ALBUMINFO = "保存AlbumInfo.txt"
    SETTING_DOWNLOAD_VIDEOS = "Download videos"
    SETTING_ADD_LRC_FILE = "保存歌词文件 (.lrc file)"
    SETTING_PATH = "配置文件目录"
    SETTING_APIKEY = "APIKey支持"
    SETTING_DOWNLOAD_DELAY = "Use Download Delay"

    PRINT_ERR = "[错误]"
    PRINT_INFO = "[提示]"
    PRINT_SUCCESS = "[成功]"

    PRINT_LATEST_VERSION = "最新版本:"

    CHANGE_DOWNLOAD_PATH = "下载路径('0' 不修改):"
    CHANGE_AUDIO_QUALITY = "音频质量('0'-Normal,'1'-High,'2'-HiFi,'3'-Master,'4'-Max):"
    CHANGE_VIDEO_QUALITY = "视频质量(1080, 720, 480, 360):"
    CHANGE_CHECK_EXIST = "下载前检查是否有已下载的文件('0'-不,'1'-是):"
    CHANGE_INCLUDE_EP = "下载歌手专辑时包含其EP单曲('0'-不,'1'-是):"
    CHANGE_SAVE_COVERS = "保存封面('0'-不,'1'-是):"
    CHANGE_LANGUAGE = "选择语言"
    CHANGE_ALBUM_FOLDER_FORMAT = "专辑目录格式('0' 不修改):"
    CHANGE_PLAYLIST_FOLDER_FORMAT = "Playlist folder format('0'-not modify,'default'-to set default):"
    CHANGE_TRACK_FILE_FORMAT = "歌曲文件名格式('0' 不修改):"
    CHANGE_VIDEO_FILE_FORMAT = "视频文件名格式('0'-not modify,'default'-to set default):"
    CHANGE_SHOW_PROGRESS = "显示进度条('0'-不,'1'-是):"
    CHANGE_SHOW_TRACKINFO = "显示歌曲信息('0'-否,'1'-是):"
    CHANGE_SAVE_ALBUM_INFO = "保存AlbumInfo.txt('0'-否,'1'-是):"
    CHANGE_DOWNLOAD_VIDEOS = "Download videos (when downloading playlists, albums, mixes)('0'-No,'1'-Yes):"
    CHANGE_ADD_LRC_FILE = "保存歌词文件 ('0'-否,'1'-是):"
    CHANGE_MULITHREAD_DOWNLOAD = "多线程下载('0'-否,'1'-是):"
    CHANGE_USE_DOWNLOAD_DELAY = "Use Download Delay('0'-No,'1'-Yes):"

    # {} are required in these strings
    AUTH_START_LOGIN = "开始启动登录..."
    AUTH_NEXT_STEP = "请打开 {} 并在 {} 之内完成操作."
    AUTH_WAITING = "等待登录验证..."
    AUTH_TIMEOUT = "操作超时."

    MSG_VALID_ACCESSTOKEN = "AccessToken有效期为 {}."
    MSG_INVALID_ACCESSTOKEN = "AccessToken失效. 正在尝试更新它."
    MSG_PATH_ERR = "路径错误!"
    MSG_INPUT_ERR = "输入错误!"

    MODEL_ALBUM_PROPERTY = "专辑信息"
    MODEL_TRACK_PROPERTY = "歌曲信息"
    MODEL_VIDEO_PROPERTY = "视频信息"
    MODEL_ARTIST_PROPERTY = "歌手信息"
    MODEL_PLAYLIST_PROPERTY = "歌单信息"

    MODEL_TITLE = '标题'
    MODEL_TRACK_NUMBER = '歌曲数量'
    MODEL_VIDEO_NUMBER = '视频数量'
    MODEL_RELEASE_DATE = '发布时间'
    MODEL_VERSION = '版本'
    MODEL_EXPLICIT = '脏标'
    MODEL_ALBUM = '专辑'
    MODEL_ID = 'ID'
    MODEL_NAME = '名称'
    MODEL_TYPE = '类型'
