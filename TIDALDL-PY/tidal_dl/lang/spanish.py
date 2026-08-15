#!/usr/bin/env python
# -*- encoding: utf-8 -*-
'''
@File    :   spanish.py
@Time    :   2022/07/07
@Author  :   Frikilinux & JavierSC
@Version :   2.3
@Contact :
@Desc    :
'''

class LangSpanish(object):
    SETTING = "AJUSTES"
    VALUE = "VALORES"
    SETTING_DOWNLOAD_PATH = "Ruta de descarga"
    SETTING_AUDIO_QUALITY = "Calidad de audio"
    SETTING_VIDEO_QUALITY = "Calidad de video"
    SETTING_CHECK_EXIST = "Verificar si existe"
    SETTING_INCLUDE_EP = "Incluir sencillos y EPs"
    SETTING_SAVE_COVERS = "Guardar carátulas"
    SETTING_LANGUAGE = "Idioma"
    SETTING_USE_PLAYLIST_FOLDER = "Usar directorio de la lista de reproducción"
    SETTING_MULITHREAD_DOWNLOAD = "Descarga Multi-hilo"
    SETTING_ALBUM_FOLDER_FORMAT = "Formato del nombre de carpeta del álbum"
    SETTING_PLAYLIST_FOLDER_FORMAT = "Playlist folder format"
    SETTING_TRACK_FILE_FORMAT = "Formato del nombre de archivo de la pista"
    SETTING_VIDEO_FILE_FORMAT = "Video file format"
    SETTING_SHOW_PROGRESS = "Mostrar progreso"
    SETTING_SHOW_TRACKINFO = "Mostrar información de pista"
    SETTING_SAVE_ALBUMINFO = "Guardar AlbumInfo.txt"
    SETTING_DOWNLOAD_VIDEOS = "Download videos"
    SETTING_ADD_LRC_FILE = "Añadir letras cronometradas (archivo .lrc)"
    SETTING_PATH = "Ruta de ajustes"
    SETTING_APIKEY = "Soporte de la APIKey"
    SETTING_DOWNLOAD_DELAY = "Use Download Delay"

    PRINT_ERR = "[ERROR]"
    PRINT_INFO = "[INFO]"
    PRINT_SUCCESS = "[ÉXITO]"

    PRINT_LATEST_VERSION = "Última versión:"

    CHANGE_DOWNLOAD_PATH = "Ruta de descarga ('0' No modificar):"
    CHANGE_AUDIO_QUALITY = "Calidad de audio ('0'-Normal,'1'-High,'2'-HiFi,'3'-Master,'4'-Max):"
    CHANGE_VIDEO_QUALITY = "Calidad de video (1080, 720, 480, 360):"
    CHANGE_CHECK_EXIST = "¿Verificar si el archivo existe antes de descargar la pista? ('0'-No,'1'-Sí):"
    CHANGE_INCLUDE_EP = "¿Incluir Sencillos y EPs al descargar el álbum del artista? ('0'-No,'1'-Sí):"
    CHANGE_SAVE_COVERS = "¿Guardar carátulas?('0'-No,'1'-Sí):"
    CHANGE_LANGUAGE = "Seleccione el idioma"
    CHANGE_ALBUM_FOLDER_FORMAT = "Formato del nombre de carpeta del álbum ('0' No modificar):"
    CHANGE_PLAYLIST_FOLDER_FORMAT = "Playlist folder format('0'-not modify,'default'-to set default):"
    CHANGE_TRACK_FILE_FORMAT = "Formato del nombre de archivo de la pista ('0' No modificar):"
    CHANGE_VIDEO_FILE_FORMAT = "Formato del archivo de video('0'-No modificar,'default'-por defecto):"
    CHANGE_SHOW_PROGRESS = "¿Mostrar progreso? ('0'-No,'1'-Sí):"
    CHANGE_SHOW_TRACKINFO = "¿Mostrar información de pista?('0'-No,'1'-Sí):"
    CHANGE_SAVE_ALBUM_INFO = "¿Guardar AlbumInfo.txt?('0'-No,'1'-Sí):"
    CHANGE_DOWNLOAD_VIDEOS = "Download videos (when downloading playlists, albums, mixes)('0'-No,'1'-Yes):"
    CHANGE_ADD_LRC_FILE = "¿Añadir letras cronometradas en un archivo .lrc? ('0'-No,'1'-Sí):"
    CHANGE_MULITHREAD_DOWNLOAD = "¿Descarga Multi-hilo?('0'-No,'1'-Sí:"
    CHANGE_USE_DOWNLOAD_DELAY = "Use Download Delay('0'-No,'1'-Yes):"

    # {} are required in these strings
    AUTH_START_LOGIN = "Iniciando sesión..."
    AUTH_NEXT_STEP = "Diríjase a {} en los próximos {} para completar la autorización."
    AUTH_WAITING = "Esperando la autorización..."
    AUTH_TIMEOUT = "Se superó el tiempo de espera."

    MSG_VALID_ACCESSTOKEN = "Token de acceso válido por {}."
    MSG_INVALID_ACCESSTOKEN = "El token de acceso ha expirado. Tratando de renovarlo."
    MSG_PATH_ERR = "¡La ruta no es correcta!"
    MSG_INPUT_ERR = "¡Error de entrada!"

    MODEL_ALBUM_PROPERTY = "PROPIEDAD-DE-ÁLBUM"
    MODEL_TRACK_PROPERTY = "PROPIEDAD-DE-PISTA"
    MODEL_VIDEO_PROPERTY = "PROPIEDAD-DE-VIDEO"
    MODEL_ARTIST_PROPERTY = "PROPIEDAD-DE-ARTISTA"
    MODEL_PLAYLIST_PROPERTY = "PROPIEDAD-DE-PLAYLIST"

    MODEL_TITLE = 'Título'
    MODEL_TRACK_NUMBER = 'Número de pistas'
    MODEL_VIDEO_NUMBER = 'Número de videos'
    MODEL_RELEASE_DATE = 'Fecha de lanzamiento'
    MODEL_VERSION = 'Versión'
    MODEL_EXPLICIT = 'Explícito'
    MODEL_ALBUM = 'Álbum'
    MODEL_ID = 'ID'
    MODEL_NAME = 'Nombre'
    MODEL_TYPE = 'Tipo'
