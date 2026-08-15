#!/usr/bin/env python
# -*- encoding: utf-8 -*-
'''
@File    :   ukrainian.py
@Time    :   2022/02/20
@Author  :   Montyzzz & 9uyone
@Version :   1.2
@Contact :   ---
@Desc    :
'''

class LangUkrainian(object):
    SETTING = "НАЛАШТУВАННЯ"
    VALUE = "ЗНАЧЕННЯ"
    SETTING_DOWNLOAD_PATH = "Шлях завантаження"
    SETTING_AUDIO_QUALITY = "Якість аудіо"
    SETTING_VIDEO_QUALITY = "Якість відео"
    SETTING_CHECK_EXIST = "Перевіряти наявність"
    SETTING_INCLUDE_EP = "Включати сингли та міньйони (EP)"
    SETTING_SAVE_COVERS = "Зберігати обкладинки"
    SETTING_LANGUAGE = "Мова"
    SETTING_USE_PLAYLIST_FOLDER = "Використовувати папку плейлиста"
    SETTING_MULITHREAD_DOWNLOAD = "Багатопоточне завантаження"
    SETTING_ALBUM_FOLDER_FORMAT = "Формат папки альбому"
    SETTING_PLAYLIST_FOLDER_FORMAT = "Playlist folder format"
    SETTING_TRACK_FILE_FORMAT = "Формат файлу треку"
    SETTING_VIDEO_FILE_FORMAT = "Video file format"
    SETTING_SHOW_PROGRESS = "Показувати прогрес"
    SETTING_SHOW_TRACKINFO = "Показувати інформацію про трек"
    SETTING_SAVE_ALBUMINFO = "Зберігати AlbumInfo.txt"
    SETTING_DOWNLOAD_VIDEOS = "Download videos"
    SETTING_ADD_LRC_FILE = "Зберігати тексти з відмітками часу (.lrc файл)"
    SETTING_PATH = "Шлях налаштувань"
    SETTING_APIKEY = "Підтримка ключа API"
    SETTING_DOWNLOAD_DELAY = "Use Download Delay"

    PRINT_ERR = "[ПОМИЛКА]"
    PRINT_INFO = "[ІНФОРМАЦІЯ]"
    PRINT_SUCCESS = "[УСПІХ]"

    PRINT_LATEST_VERSION = "Остання версія:"

    CHANGE_DOWNLOAD_PATH = "Шлях завантаження('0'-не змінювати):"
    CHANGE_AUDIO_QUALITY = "Якість аудіо('0'-Звичайна,'1'-Висока,'2'-HiFi,'3'-MQA,'4'-Max):"
    CHANGE_VIDEO_QUALITY = "Якість відео(1080,720,480,360):"
    CHANGE_CHECK_EXIST = "Перевіряти наявний файл перед завантаженням треку('0'-Ні,'1'-Так):"
    CHANGE_INCLUDE_EP = "Включати сингли та міньйони під час завантаження альбомів виконавця('0'-Ні,'1'-Так):"
    CHANGE_SAVE_COVERS = "Зберігати обкладинки('0'-Ні,'1'-Так):"
    CHANGE_LANGUAGE = "Обрати мову"
    CHANGE_ALBUM_FOLDER_FORMAT = "Формат теки альбому('0'-не змінювати):"
    CHANGE_PLAYLIST_FOLDER_FORMAT = "Playlist folder format('0'-not modify,'default'-to set default):"
    CHANGE_TRACK_FILE_FORMAT = "Формат файлу треку('0'-не змінювати):"
    CHANGE_VIDEO_FILE_FORMAT = "Video file format('0'-not modify,'default'-to set default):"
    CHANGE_SHOW_PROGRESS = "Показувати прогрес('0'-Ні,'1'-Так):"
    CHANGE_SHOW_TRACKINFO = "Показувати інформацію про трек('0'-Ні,'1'-Так):"
    CHANGE_SAVE_ALBUM_INFO = "Зберігати AlbumInfo.txt('0'-Ні,'1'-Так):"
    CHANGE_DOWNLOAD_VIDEOS = "Download videos (when downloading playlists, albums, mixes)('0'-No,'1'-Yes):"
    CHANGE_ADD_LRC_FILE = "Зберігати тексти пісень з відмітками часу в .lrc файл('0'-Ні,'1'-Так):"
    CHANGE_MULITHREAD_DOWNLOAD = "Multi thread download('0'-No,'1'-Yes):"
    CHANGE_USE_DOWNLOAD_DELAY = "Use Download Delay('0'-No,'1'-Yes):"

    # {} are required in these strings
    AUTH_START_LOGIN = "Початок процесу авторизації..."
    AUTH_NEXT_STEP = "Зайдіть на {} протягом наступних {} для завершення налаштування."
    AUTH_WAITING = "Очікування авторизації..."
    AUTH_TIMEOUT = "Час очікування минув."

    MSG_VALID_ACCESSTOKEN = "AccessToken хороший упродовж {}."
    MSG_INVALID_ACCESSTOKEN = "Термін дії AccessToken'а закінчився. Пробуємо оновити його."
    MSG_PATH_ERR = "Невірний шлях!"
    MSG_INPUT_ERR = "Помилка введення!"

    MODEL_ALBUM_PROPERTY = "АЛЬБОМ-ВЛАСТИВІСТЬ"
    MODEL_TRACK_PROPERTY = "ТРЕК-ВЛАСТИВІСТЬ"
    MODEL_VIDEO_PROPERTY = "ВІДЕО-ВЛАСТИВІСТЬ"
    MODEL_ARTIST_PROPERTY = "АРТИСТ-ВЛАСТИВІСТЬ"
    MODEL_PLAYLIST_PROPERTY = "ПЛЕЙЛИСТ-ВЛАСТИВІСТЬ"

    MODEL_TITLE = 'Назва'
    MODEL_TRACK_NUMBER = 'Номер доріжки'
    MODEL_VIDEO_NUMBER = 'Номер відео'
    MODEL_RELEASE_DATE = 'Дата релізу'
    MODEL_VERSION = 'Версія'
    MODEL_EXPLICIT = 'Нецензурно'
    MODEL_ALBUM = 'Альбом'
    MODEL_ID = 'ID'
    MODEL_NAME = 'Ім\'я'
    MODEL_TYPE = 'Тип'
