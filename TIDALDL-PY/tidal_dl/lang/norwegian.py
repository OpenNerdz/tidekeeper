#!/usr/bin/env python
# -*- encoding: utf-8 -*-
'''
@File    :   norwegian.py
@Time    :   2021/03/25
@Author  :   roberts91
@Version :   1.0
@Contact :   
@Desc    :   
'''

class LangNorwegian(object):
    SETTING = "INNSTILLINGER"
    VALUE = "Verdi"
    SETTING_DOWNLOAD_PATH = "Nedlastingssti"
    SETTING_AUDIO_QUALITY = "Lydkvalitet"
    SETTING_VIDEO_QUALITY = "Videokvalitet"
    SETTING_CHECK_EXIST = "Kontroller eksistens"
    SETTING_INCLUDE_EP = "Inkluder single&EP"
    SETTING_SAVE_COVERS = "Lagre cover"
    SETTING_LANGUAGE = "Språk"
    SETTING_USE_PLAYLIST_FOLDER = "Bruk spillelistemappe"
    SETTING_MULITHREAD_DOWNLOAD = "Last ned flere samtidig"
    SETTING_ALBUM_FOLDER_FORMAT = "Albummappens format"
    SETTING_PLAYLIST_FOLDER_FORMAT = "Spillelistemappens format"
    SETTING_TRACK_FILE_FORMAT = "Spor filformat"
    SETTING_VIDEO_FILE_FORMAT = "Video filformat"
    SETTING_SHOW_PROGRESS = "Vis fremgang"
    SETTING_SHOW_TRACKINFO = "Vis sporinformasjon"
    SETTING_SAVE_ALBUMINFO = "Lagre AlbumInfo.txt"
    SETTING_DOWNLOAD_VIDEOS = "Last ned video"
    SETTING_ADD_LRC_FILE = "Lagre sangtekster med tidsreferanser (.lrc fil)"
    SETTING_PATH = "Innstillinger sti"
    SETTING_APIKEY = "API-nøkkel støtte"
    SETTING_DOWNLOAD_DELAY = "Use Download Delay"

    PRINT_ERR = "[FEIL]"
    PRINT_INFO = "[INFO]"
    PRINT_SUCCESS = "[SUCCES]"

    PRINT_LATEST_VERSION = "Seneste versjon:"

    CHANGE_DOWNLOAD_PATH = "Nedlastingssti('0'-ikke endre):"
    CHANGE_AUDIO_QUALITY = "Lydkvalitet('0'-Normal,'1'-Høy,'2'-HiFi,'3'-Master,'4'-Max):"
    CHANGE_VIDEO_QUALITY = "Videokvalitet(1080, 720, 480, 360):"
    CHANGE_CHECK_EXIST = "Kontrollér filens eksistens før nedlasting('0'-Nei,'1'-Ja):"
    CHANGE_INCLUDE_EP = "Inkluder singler og EP'er når man laster ned en artists album('0'-Nei,'1'-Ja):"
    CHANGE_SAVE_COVERS = "Lagre cover('0'-Nei,'1'-Ja):"
    CHANGE_LANGUAGE = "Velg språk"
    CHANGE_ALBUM_FOLDER_FORMAT = "Albummappe format('0'-ikke endre, 'default'-for å sette til standardverdi):"
    CHANGE_PLAYLIST_FOLDER_FORMAT = "Spillelistemappe format('0'-ikke endre, 'default'-for å sette til standardverdi):"
    CHANGE_TRACK_FILE_FORMAT = "Sportittel filformat('0'-ikke endre, 'default'-for å sette til standardverdi):"
    CHANGE_VIDEO_FILE_FORMAT = "Videofil format('0'-ikke endre, 'default'-for å sette til standardverdi):"
    CHANGE_SHOW_PROGRESS = "Vis fremgang('0'-Nei,'1'-Ja):"
    CHANGE_SHOW_TRACKINFO = "Vis sporinformasjon('0'-Nei,'1'-Ja):"
    CHANGE_SAVE_ALBUM_INFO = "Lagre AlbumInfo.txt('0'-Nei,'1'-Ja):"
    CHANGE_DOWNLOAD_VIDEOS = "Last ned videers (i spillelister, album, mikser)('0'-No,'1'-Yes):"
    CHANGE_ADD_LRC_FILE = "Lagre sangtekster med tidsreferanser .lrc fil ('0'-Nei,'1'-Ja):"
    CHANGE_MULITHREAD_DOWNLOAD = "Last ned flere samtidig('0'-Nei,'1'-Ja):"
    CHANGE_USE_DOWNLOAD_DELAY = "Use Download Delay('0'-No,'1'-Yes):"

    # {} are required in these strings
    AUTH_START_LOGIN = "Starter login-prosessen."
    AUTH_NEXT_STEP = "Gå til {} innen de neste {} for å avslutte setup."
    AUTH_WAITING = "Venter på godkjennelse..."
    AUTH_TIMEOUT = "Tiden gikk ut."

    MSG_VALID_ACCESSTOKEN = "AccessToken tilgjengelig for {}."
    MSG_INVALID_ACCESSTOKEN = "AccessToken utløpt. Forøsker å oppdatere"
    MSG_PATH_ERR = "Sti feil!"
    MSG_INPUT_ERR = "Inntastningsfeol!"

    MODEL_ALBUM_PROPERTY = "ALBUM-PROPERTY"
    MODEL_TRACK_PROPERTY = "TRACK-PROPERTY"
    MODEL_VIDEO_PROPERTY = "VIDEO-PROPERTY"
    MODEL_ARTIST_PROPERTY = "ARTIST-PROPERTY"
    MODEL_PLAYLIST_PROPERTY = "PLAYLIST-PROPERTY"

    MODEL_TITLE = 'Tittel'
    MODEL_TRACK_NUMBER = 'Spornummer'
    MODEL_VIDEO_NUMBER = 'Videonummer'
    MODEL_RELEASE_DATE = 'Utgivelsesdato'
    MODEL_VERSION = 'Versjon'
    MODEL_EXPLICIT = 'Eksplisitt'
    MODEL_ALBUM = 'Album'
    MODEL_ID = 'ID'
    MODEL_NAME = 'Navn'
    MODEL_TYPE = 'Type'
