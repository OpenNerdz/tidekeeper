#!/usr/bin/env python
# -*- encoding: utf-8 -*-
'''
@File    :   french.py
@Time    :   2020/10/25
@Authors :   flamme-demon & joyel24
@Version :   0.3
@Contact :
@Desc    :
'''

class LangFrench(object):
    SETTING = "RÉGLAGES"
    VALUE = "VALEUR"
    SETTING_DOWNLOAD_PATH = "Emplacement des téléchargements"
    SETTING_AUDIO_QUALITY = "Qualité Audio"
    SETTING_VIDEO_QUALITY = "Qualité Video"
    SETTING_CHECK_EXIST = "Vérifier l'existence"
    SETTING_INCLUDE_EP = "Inclure les singles & EPs"
    SETTING_SAVE_COVERS = "Sauvegarder les couvertures"
    SETTING_LANGUAGE = "Langue"
    SETTING_USE_PLAYLIST_FOLDER = "Utiliser dossier de playlist"
    SETTING_MULITHREAD_DOWNLOAD = "Téléchargement multithread"
    SETTING_ALBUM_FOLDER_FORMAT = "Format du dossier d'album"
    SETTING_PLAYLIST_FOLDER_FORMAT = "Playlist folder format"
    SETTING_TRACK_FILE_FORMAT = "Format du fichier de tracklist"
    SETTING_VIDEO_FILE_FORMAT = "Video file format"
    SETTING_SHOW_PROGRESS = "Afficher la Progression"
    SETTING_SHOW_TRACKINFO = "Afficher les information de la musique"
    SETTING_SAVE_ALBUMINFO = "Enregistrer AlbumInfo.txt"
    SETTING_DOWNLOAD_VIDEOS = "Download videos"
    SETTING_ADD_LRC_FILE = "Enregistrer les paroles synchronisées (fichier .lrc)"
    SETTING_PATH = "Emplacement des paramètres"
    SETTING_APIKEY = "Prise en charge de la clé API"
    SETTING_DOWNLOAD_DELAY = "Use Download Delay"

    PRINT_ERR = "[ERR]"
    PRINT_INFO = "[INFO]"
    PRINT_SUCCESS = "[SUCCES]"

    PRINT_LATEST_VERSION = "Dernière version:"

    CHANGE_DOWNLOAD_PATH = "Emplacement des téléchargements('0' ne pas modifier):"
    CHANGE_AUDIO_QUALITY = "Qualité audio('0'-Normal,'1'-High,'2'-HiFi,'3'-Master,'4'-Max):"
    CHANGE_VIDEO_QUALITY = "Qualité Video(1080, 720, 480, 360):"
    CHANGE_CHECK_EXIST = "Vérifier l'existence du fichier avant le téléchargement('0'-Non,'1'-Oui):"
    CHANGE_INCLUDE_EP = "Inclure les singles et les EPs lors du téléchargement des albums d'un artiste('0'-Non,'1'-Oui):"
    CHANGE_SAVE_COVERS = "Sauvegarder les couvertures('0'-Non,'1'-Oui):"
    CHANGE_LANGUAGE = "Sélectionnez une langue"
    CHANGE_ALBUM_FOLDER_FORMAT = "Format du dossier d'album('0' ne pas modifier):"
    CHANGE_PLAYLIST_FOLDER_FORMAT = "Playlist folder format('0'-not modify,'default'-to set default):"
    CHANGE_TRACK_FILE_FORMAT = "Format du fichier de tracklist('0' ne pas modifier):"
    CHANGE_VIDEO_FILE_FORMAT = "Video file format('0'-not modify,'default'-to set default):"
    CHANGE_SHOW_PROGRESS = "Afficher la progression('0'-Non,'1'-Oui):"
    CHANGE_SHOW_TRACKINFO = "Afficher les information de la piste ('0'-Non,'1'-Oui):"
    CHANGE_SAVE_ALBUM_INFO = "Enregistrer AlbumInfo.txt('0'-Non,'1'-Oui):"
    CHANGE_DOWNLOAD_VIDEOS = "Download videos (when downloading playlists, albums, mixes)('0'-No,'1'-Yes):"
    CHANGE_ADD_LRC_FILE = "Enregistrer les paroles synchronisées (fichier.lrc) ('0'-Non,'1'-Oui):"
    CHANGE_MULITHREAD_DOWNLOAD = "Multi thread download('0'-Non,'1'-Oui):"
    CHANGE_USE_DOWNLOAD_DELAY = "Use Download Delay('0'-No,'1'-Yes):"

    # {} are required in these strings
    AUTH_START_LOGIN = "Démarrage du processus de connexion..."
    AUTH_NEXT_STEP = "Allez à {} avant {} pour finir la configuration."
    AUTH_WAITING = "En attente d'autorisation..."
    AUTH_TIMEOUT = "Temps écoulé."

    MSG_VALID_ACCESSTOKEN = "Token d'accès valable {}."
    MSG_INVALID_ACCESSTOKEN = "Token d'accès expiré. Tentative de renouvellement automatique."
    MSG_PATH_ERR = "Erreur du chemin d'accès"
    MSG_INPUT_ERR = "Erreur de saisie !"

    MODEL_ALBUM_PROPERTY = "PROPRIETES-ALBUM"
    MODEL_TRACK_PROPERTY = "PROPRIETES-PISTES-AUDIO"
    MODEL_VIDEO_PROPERTY = "PROPRIETES-VIDEO"
    MODEL_ARTIST_PROPERTY = "PROPRIETES-ARTISTE"
    MODEL_PLAYLIST_PROPERTY = "PROPERTES-PLAYLIST"

    MODEL_TITLE = 'Titre'
    MODEL_TRACK_NUMBER = 'Numéro de piste'
    MODEL_VIDEO_NUMBER = 'Numéro de la vidéo'
    MODEL_RELEASE_DATE = 'Date de publication'
    MODEL_VERSION = 'Version'
    MODEL_EXPLICIT = 'Explicit'
    MODEL_ALBUM = 'Album'
    MODEL_ID = 'ID'
    MODEL_NAME = 'Nom'
    MODEL_TYPE = 'Type'
