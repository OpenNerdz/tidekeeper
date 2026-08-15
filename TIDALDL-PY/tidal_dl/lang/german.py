#!/usr/bin/env python
# -*- encoding: utf-8 -*-
'''
@File    :   german.py
@Time    :   2022/11/8
@Authors :   Sematre, MineClashTV, Click1701
@Version :   1.1
@Contact :
@Desc    :
'''

class LangGerman(object):
    SETTING = "EINSTELLUNG"
    VALUE = "WERT"
    SETTING_DOWNLOAD_PATH = "Download Pfad"
    SETTING_AUDIO_QUALITY = "Tonqualität"
    SETTING_VIDEO_QUALITY = "Videoqualität"
    SETTING_CHECK_EXIST = "Existenz überprüfen"
    SETTING_INCLUDE_EP = "Singles & EPs einschließen"
    SETTING_SAVE_COVERS = "Cover speichern"
    SETTING_LANGUAGE = "Sprache"
    SETTING_USE_PLAYLIST_FOLDER = "Playlist-Ordner verwenden"
    SETTING_MULITHREAD_DOWNLOAD = "Multi-Thread Download"
    SETTING_ALBUM_FOLDER_FORMAT = "Album-Ordnerformat"
    SETTING_PLAYLIST_FOLDER_FORMAT = "Playlist-Ordnerformat"
    SETTING_TRACK_FILE_FORMAT = "Track-Dateiformat"
    SETTING_VIDEO_FILE_FORMAT = "Video-Dateiformat"
    SETTING_SHOW_PROGRESS = "Fortschritt anzeigen"
    SETTING_SHOW_TRACKINFO = "Titelinformationen anzeigen"
    SETTING_SAVE_ALBUMINFO = "AlbumInfo.txt speichern"
    SETTING_DOWNLOAD_VIDEOS = "Download videos"
    SETTING_ADD_LRC_FILE = "Songtext mit Zeitcode speichern (.lrc Datei)"
    SETTING_PATH = "Speicherort der Einstellungen"
    SETTING_APIKEY = "APIKey Unterstützung"
    SETTING_DOWNLOAD_DELAY = "Downloads zeitverzögert starten"

    PRINT_ERR = "[FEHLER]"
    PRINT_INFO = "[INFO]"
    PRINT_SUCCESS = "[ERFOLG]"

    PRINT_LATEST_VERSION = "Neueste Version:"

    CHANGE_DOWNLOAD_PATH = "Downloadpfad ('0' nicht ändern):"
    CHANGE_AUDIO_QUALITY = "Tonqualität ('0'-Normal, '1'-Hoch, '2'-HiFi, '3'-Master,'4'-Max):"
    CHANGE_VIDEO_QUALITY = "Videoqualität (1080, 720, 480, 360):"
    CHANGE_CHECK_EXIST = "Vor dem Download überprüfen, ob die Datei existiert ('0'-Nein, '1'-Ja):"
    CHANGE_INCLUDE_EP = "Singles und EPs beim Download von Alben eines Künstlers einbeziehen ('0'-Nein, '1'-Ja):"
    CHANGE_SAVE_COVERS = "Cover speichern ('0'-Nein, '1'-Ja):"
    CHANGE_LANGUAGE = "Sprache auswählen"
    CHANGE_ALBUM_FOLDER_FORMAT = "Album-Ordnerformat ('0' überspringen):"
    CHANGE_PLAYLIST_FOLDER_FORMAT = "Playlist Ordner-Format ('0'-nicht ändern, 'default'-für Standard):"
    CHANGE_TRACK_FILE_FORMAT = "Track-Dateiformat ('0' überspringen):"
    CHANGE_VIDEO_FILE_FORMAT = "Video-Dateiformat ('0'-nicht ändern, 'default'-für Standard):"
    CHANGE_SHOW_PROGRESS = "Fortschritt anzeigen ('0'-Nein, '1'-Ja):"
    CHANGE_SHOW_TRACKINFO = "Song-Informationen anzeigen ('0'-Nein, '1'-Ja):"
    CHANGE_SAVE_ALBUM_INFO = "AlbumInfo.txt speichern ('0'-Nein, '1'-Ja):"
    CHANGE_DOWNLOAD_VIDEOS = "Download videos (when downloading playlists, albums, mixes)('0'-No,'1'-Yes):"
    CHANGE_ADD_LRC_FILE = "Songtexte mit Zeitcode speichern (.lrc Datei) ('0'-Nein, '1'-Ja):"
    CHANGE_MULITHREAD_DOWNLOAD = "Multi-Thread Download('0'-Nein, '1'-Ja):"
    CHANGE_USE_DOWNLOAD_DELAY = "Downloads zeitverzögert starten ('0'-nein, '1'-ja):"

    # {} are required in these strings
    AUTH_START_LOGIN = "Starte Loginprozess..."
    AUTH_NEXT_STEP = "Gehe auf {} in den nächsten {} um das Setup abzuschließen."
    AUTH_WAITING = "Warte auf Autorisierung..."
    AUTH_TIMEOUT = "Zeitüberschreitung der Operation."

    MSG_VALID_ACCESSTOKEN = "AccessToken gültig für {}."
    MSG_INVALID_ACCESSTOKEN = "AccessToken abgelaufen. Er muss erneuert werden."
    MSG_PATH_ERR = "Ungültiger Pfad!"
    MSG_INPUT_ERR = "Eingabefehler!"

    MODEL_ALBUM_PROPERTY = "ALBUM-EIGENSCHAFT"
    MODEL_TRACK_PROPERTY = "TRACK-EIGENSCHAFT"
    MODEL_VIDEO_PROPERTY = "VIDEO-EIGENSCHAFT"
    MODEL_ARTIST_PROPERTY = "KÜNSTLER-EIGENSCHAFT"
    MODEL_PLAYLIST_PROPERTY = "PLAYLIST-EIGENSCHAFT"

    MODEL_TITLE = 'Titel'
    MODEL_TRACK_NUMBER = 'Titelnummer'
    MODEL_VIDEO_NUMBER = 'Videonummer'
    MODEL_RELEASE_DATE = 'Veröffentlichungsdatum'
    MODEL_VERSION = 'Version'
    MODEL_EXPLICIT = 'Explicit'
    MODEL_ALBUM = 'Album'
    MODEL_ID = 'ID'
    MODEL_NAME = 'Name'
    MODEL_TYPE = 'Typ'
