#!/usr/bin/env python
# -*- encoding: utf-8 -*-
'''
@File    :   russian.py
@Time    :   2020/11/29
@Author  :   sergey.seve-s
@Version :   1.0
@Contact :
@Desc    :
'''

class LangRussian(object):
    SETTING = "НАСТРОЙКА"
    VALUE = "УСТАНОВКА"
    SETTING_DOWNLOAD_PATH = "Место сохранения"
    SETTING_AUDIO_QUALITY = "Качество аудио"
    SETTING_VIDEO_QUALITY = "Качество видео"
    SETTING_CHECK_EXIST = "Проверять наличие"
    SETTING_INCLUDE_EP = "Включить сингл и миньон"
    SETTING_SAVE_COVERS = "Добавлять обложку"
    SETTING_LANGUAGE = "Язык"
    SETTING_USE_PLAYLIST_FOLDER = "Плейлисты в отдельную папку"
    SETTING_MULITHREAD_DOWNLOAD = "Многопоточная загрузка"
    SETTING_ALBUM_FOLDER_FORMAT = "Маска имени альбома"
    SETTING_PLAYLIST_FOLDER_FORMAT = "Playlist folder format"
    SETTING_TRACK_FILE_FORMAT = "Маска имени трека"
    SETTING_VIDEO_FILE_FORMAT = "Video file format"
    SETTING_SHOW_PROGRESS = "Показывать процесс загрузки"
    SETTING_SHOW_TRACKINFO = "Show Track Info"
    SETTING_SAVE_ALBUMINFO = "Сохранять AlbumInfo.txt"
    SETTING_DOWNLOAD_VIDEOS = "Download videos"
    SETTING_ADD_LRC_FILE = "Save timed lyrics (.lrc file)"
    SETTING_PATH = "Путь для настроек"
    SETTING_APIKEY = "APIKey support"
    SETTING_DOWNLOAD_DELAY = "Use Download Delay"

    PRINT_ERR = "[ОШИБКА]"
    PRINT_INFO = "[СВЕДЕНИЯ]"
    PRINT_SUCCESS = "[ГОТОВО]"

    PRINT_LATEST_VERSION = "Последняя версия:"

    CHANGE_DOWNLOAD_PATH = "Место сохранения('0'-Отмена):"
    CHANGE_AUDIO_QUALITY = "Качество аудио('0'-Стандарт,'1'-Высокое,'2'-HiFi,'3'-MQA,'4'-Max):"
    CHANGE_VIDEO_QUALITY = "Качество видео(1080, 720, 480, 360):"
    CHANGE_CHECK_EXIST = "Проверять наличие перед загрузкой('0'-Нет,'1'-Да):"
    CHANGE_INCLUDE_EP = "Включать синглы и миньоны в дискографию('0'-Нет'1'-Да):"
    CHANGE_SAVE_COVERS = "Сохранять обложки('0'-Нет,'1'-Да):"
    CHANGE_LANGUAGE = "Выбрать язык"
    CHANGE_ALBUM_FOLDER_FORMAT = "Маска имени альбома('0' не менять):"
    CHANGE_PLAYLIST_FOLDER_FORMAT = "Playlist folder format('0'-not modify,'default'-to set default):"
    CHANGE_TRACK_FILE_FORMAT = "Маска имени трека('0' не менять):"
    CHANGE_VIDEO_FILE_FORMAT = "Video file format('0'-not modify,'default'-to set default):"
    CHANGE_SHOW_PROGRESS = "Показывать процесс загрузки('0'-Нет,'1'-Да):"
    CHANGE_SHOW_TRACKINFO = "Show track info('0'-No,'1'-Yes):"
    CHANGE_SAVE_ALBUM_INFO = "Сохранять AlbumInfo.txt('0'-Нет,'1'-Да):"
    CHANGE_DOWNLOAD_VIDEOS = "Download videos (when downloading playlists, albums, mixes)('0'-No,'1'-Yes):"
    CHANGE_ADD_LRC_FILE = "Save timed lyrics .lrc file ('0'-No,'1'-Yes):"
    CHANGE_MULITHREAD_DOWNLOAD = "Multi thread download('0'-No,'1'-Yes):"
    CHANGE_USE_DOWNLOAD_DELAY = "Use Download Delay('0'-No,'1'-Yes):"

    # {} are required in these strings
    AUTH_START_LOGIN = "Входим в сервис..."
    AUTH_NEXT_STEP = "Перейдите к {} в течении {}, для завершения настройки."
    AUTH_WAITING = "Ожидание авторизации..."
    AUTH_TIMEOUT = "Закончилось время ожидания."

    MSG_VALID_ACCESSTOKEN = "AccessToken успешно применён {}."
    MSG_INVALID_ACCESSTOKEN = "Срок действия AccessToken истек.  Попытка обновления."
    MSG_PATH_ERR = "Неверное место!"
    MSG_INPUT_ERR = "Ошибка ввода!"

    MODEL_ALBUM_PROPERTY = "ALBUM-PROPERTY"
    MODEL_TRACK_PROPERTY = "TRACK-PROPERTY"
    MODEL_VIDEO_PROPERTY = "VIDEO-PROPERTY"
    MODEL_ARTIST_PROPERTY = "ARTIST-PROPERTY"
    MODEL_PLAYLIST_PROPERTY = "PLAYLIST-PROPERTY"

    MODEL_TITLE = 'Название'
    MODEL_TRACK_NUMBER = 'Номер трека'
    MODEL_VIDEO_NUMBER = 'Номер видео'
    MODEL_RELEASE_DATE = 'Дата издания'
    MODEL_VERSION = 'Версия'
    MODEL_EXPLICIT = 'Нецензурно'
    MODEL_ALBUM = 'Альбом'
    MODEL_ID = 'ID'
    MODEL_NAME = 'Имя'
    MODEL_TYPE = 'Тип'
