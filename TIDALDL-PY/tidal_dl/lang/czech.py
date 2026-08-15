#!/usr/bin/env python
# -*- encoding: utf-8 -*-
'''
@File    :   czech.py
@Time    :   2022/11/13
@Author  :   Tomikk & Sweder
@Version :   1.2
@Contact :   justtomikk@gmail.com & djsweder@gmail.com
@Desc    :
'''

class LangCzech(object):
    SETTING = "Nastavení"
    VALUE = "Hodnota"
    SETTING_DOWNLOAD_PATH = "Umístění staženého souboru"
    SETTING_AUDIO_QUALITY = "Kvalita hudby"
    SETTING_VIDEO_QUALITY = "Kvalita videa"
    SETTING_CHECK_EXIST = "Zkontrolovat existenci souboru"
    SETTING_INCLUDE_EP = "Zahrnout singly & EP"
    SETTING_SAVE_COVERS = "Uložit obal alba"
    SETTING_LANGUAGE = "Změna jazyka"
    SETTING_USE_PLAYLIST_FOLDER = "Používat složku playlistu"
    SETTING_MULITHREAD_DOWNLOAD = "Stahování více vlákny"
    SETTING_ALBUM_FOLDER_FORMAT = "Formát názvu složky alba"
    SETTING_PLAYLIST_FOLDER_FORMAT = "Playlist folder format"
    SETTING_TRACK_FILE_FORMAT = "Formát názvu souboru skladby"
    SETTING_VIDEO_FILE_FORMAT = "Formát názvu souboru videa"
    SETTING_SHOW_PROGRESS = "Zobrazit indikátor stavu stahování"
    SETTING_SHOW_TRACKINFO = "Zobrazit informace o skladbě"
    SETTING_SAVE_ALBUMINFO = "Uložit soubor AlbumInfo.txt"
    SETTING_DOWNLOAD_VIDEOS = "Download videos"
    SETTING_ADD_LRC_FILE = "Uložit slova skladby s časováním (soubor .lrc)"
    SETTING_PATH = "Cesta k souboru s nastavením"
    SETTING_APIKEY = "APIKey podporuje"
    SETTING_DOWNLOAD_DELAY = "Stahovat s časovou prodlevou"

    PRINT_ERR = "[Chyba]"
    PRINT_INFO = "[Info]"
    PRINT_SUCCESS = "[Staženo]"

    PRINT_LATEST_VERSION = "Nejnovější verze:"

    CHANGE_DOWNLOAD_PATH = "Umístění stažených souborů ('0' beze změny):"
    CHANGE_AUDIO_QUALITY = "Kvalita hudby ('0'-Normální,'1'-Vysoká,'2'-HiFi,'3'-Master,'4'-Max):"
    CHANGE_VIDEO_QUALITY = "Kvalita videa (1080, 720, 480, 360):"
    CHANGE_CHECK_EXIST = "Zkontrolovat existenci souboru před stažením ('0'-Ne,'1'-Ano):"
    CHANGE_INCLUDE_EP = "Při stahování alb interpreta zahrnout singly a EP ('0'-Ne,'1'-Ano):"
    CHANGE_SAVE_COVERS = "Uložit obaly alb ('0'-Ne,'1'-Ano):"
    CHANGE_LANGUAGE = "Zvolit jazyk"
    CHANGE_ALBUM_FOLDER_FORMAT = "Formát názvu složky alba ('0' beze změny):"
    CHANGE_PLAYLIST_FOLDER_FORMAT = "Playlist folder format('0'-not modify,'default'-to set default):"
    CHANGE_TRACK_FILE_FORMAT = "Formát názvu složky skladny ('0' beze změny):"
    CHANGE_VIDEO_FILE_FORMAT = "Formát názvu souboru videa ('0'-beze změny,'default'-pro nastavení výchozího názvu):"
    CHANGE_SHOW_PROGRESS = "Zobrazit indikátor stavu stahování ('0'-Ne,'1'-Ano):"
    CHANGE_SHOW_TRACKINFO = "Zobrazit info o skladbě ('0'-Ne,'1'-Ano):"
    CHANGE_SAVE_ALBUM_INFO = "Uložit soubor AlbumInfo.txt ('0'-Ne,'1'-Ano):"
    CHANGE_DOWNLOAD_VIDEOS = "Download videos (when downloading playlists, albums, mixes)('0'-No,'1'-Yes):"
    CHANGE_ADD_LRC_FILE = "Uložit slova skladby s časováním do souboru .lrc) ('0'-Ne,'1'-Ano):"
    CHANGE_MULITHREAD_DOWNLOAD = "Více vláken pro stahování ('0'-Ne,'1'-Ano):"
    CHANGE_USE_DOWNLOAD_DELAY = "Stahovat s časovou prodlevou('0'-Ne,'1'-Ano):"

    # {} are required in these strings
    AUTH_START_LOGIN = "Spouštění přihlašovacího procesu..."
    AUTH_NEXT_STEP = "K dokončení nastavení přejděte na stránku {} během následujích {}."
    AUTH_WAITING = "Čeká se na autorizaci..."
    AUTH_TIMEOUT = "Vypršel časový limit procesu."

    MSG_VALID_ACCESSTOKEN = "Přístupový token fukční pro {}."
    MSG_INVALID_ACCESSTOKEN = "Platnost přístupového tokenu vypršela. Pokouším se o obnovení."
    MSG_PATH_ERR = "Cesta neexistuje!"
    MSG_INPUT_ERR = "Chyba zadání!"

    MODEL_ALBUM_PROPERTY = "ALBUM-VLASTNOSTI"
    MODEL_TRACK_PROPERTY = "SKLADBA-VLASTNOSTI"
    MODEL_VIDEO_PROPERTY = "VIDEO-VLASTNOSTI"
    MODEL_ARTIST_PROPERTY = "INTERPRET-VLASTNOSTI"
    MODEL_PLAYLIST_PROPERTY = "PLAYLIST-VLASTNOSTI"

    MODEL_TITLE = 'Název skladby'
    MODEL_TRACK_NUMBER = 'Číslo skladby'
    MODEL_VIDEO_NUMBER = 'Číslo videa'
    MODEL_RELEASE_DATE = 'Datum vydání'
    MODEL_VERSION = 'Verze'
    MODEL_EXPLICIT = 'Explicitní'
    MODEL_ALBUM = 'Album'
    MODEL_ID = 'ID'
    MODEL_NAME = 'Jméno'
    MODEL_TYPE = 'Typ'
