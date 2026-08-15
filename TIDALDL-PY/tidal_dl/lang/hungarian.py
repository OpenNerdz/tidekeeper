#!/usr/bin/env python
# -*- encoding: utf-8 -*-
'''
@File    :   hungarian.py
@Time    :   2022/08/01
@Author  :   Shanahan
@Version :   1.2
@Contact :
@Desc    :
'''

class LangHungarian(object):
    SETTING = "BEÁLLÍTÁSOK"
    VALUE = "ÉRTÉK"
    SETTING_DOWNLOAD_PATH = "Letöltési útvonal"
    SETTING_AUDIO_QUALITY = "Audió minősége"
    SETTING_VIDEO_QUALITY = "Videó minősége"
    SETTING_CHECK_EXIST = "Ellenőrizze, hogy létezik-e"
    SETTING_INCLUDE_EP = "Tartalmazza a single&ep"
    SETTING_SAVE_COVERS = "Borítókép mentése"
    SETTING_LANGUAGE = "Nyelv"
    SETTING_USE_PLAYLIST_FOLDER = "Lejátszási lista mappa használata"
    SETTING_MULITHREAD_DOWNLOAD = "Többszálú letöltés"
    SETTING_ALBUM_FOLDER_FORMAT = "Album mappa formátum"
    SETTING_PLAYLIST_FOLDER_FORMAT = "Playlist folder format"
    SETTING_TRACK_FILE_FORMAT = "Track fájlformátum"
    SETTING_VIDEO_FILE_FORMAT = "Videó fájlformátum"
    SETTING_SHOW_PROGRESS = "Haladás megjelenítése"
    SETTING_SHOW_TRACKINFO = "Track infók megjelenítése"
    SETTING_SAVE_ALBUMINFO = "AlbumInfo.txt mentése"
    SETTING_DOWNLOAD_VIDEOS = "Download videos"
    SETTING_ADD_LRC_FILE = "Dalszövegek mentése (.lrc fájl)"
    SETTING_PATH = "Beállítási útvonal"
    SETTING_APIKEY = "APIKey támogatás"
    SETTING_DOWNLOAD_DELAY = "Use Download Delay"

    PRINT_ERR = "[HIBA]"
    PRINT_INFO = "[INFÓ]"
    PRINT_SUCCESS = "[SIKERES]"

    PRINT_LATEST_VERSION = "Legújabb verzió:"

    CHANGE_DOWNLOAD_PATH = "Letöltési útvonal('0' nincs módosítás):"
    CHANGE_AUDIO_QUALITY = "Audió minőség('0'-Normal,'1'-High,'2'-HiFi,'3'-Master,'4'-Max):"
    CHANGE_VIDEO_QUALITY = "Videó minőség(1080, 720, 480, 360):"
    CHANGE_CHECK_EXIST = "Létező fájl ellenőrzése letöltés előtt('0'-Nem,'1'-Igen):"
    CHANGE_INCLUDE_EP = "A kislemezek és EP-k letöltése('0'-Nem, '1'-Igen):"
    CHANGE_SAVE_COVERS = "Borító mentése('0'-Nem, '1'-Igen):"
    CHANGE_LANGUAGE = "Nyelv kiválasztása"
    CHANGE_ALBUM_FOLDER_FORMAT = "Album mappa formátum('0' nincs módosítás,'default' az alapértelmezett beállításhoz):"
    CHANGE_PLAYLIST_FOLDER_FORMAT = "Playlist folder format('0'-not modify,'default'-to set default):"
    CHANGE_TRACK_FILE_FORMAT = "Track fájl neve('0' nincs módosítás,'default' az alapértelmezett beállításhoz):"
    CHANGE_VIDEO_FILE_FORMAT = "Video file format('0'-nincs módosítás,'default' az alapértelmezett beállításhoz):"
    CHANGE_SHOW_PROGRESS = "Haladás megjelenítése('0'-Nem, '1'-Igen):"
    CHANGE_SHOW_TRACKINFO = "Track infók megjelenítése('0'-Nem,'1'-Igen):"
    CHANGE_SAVE_ALBUM_INFO = "AlbumInfo.txt mentése('0'-Nem, '1'-Igen):"
    CHANGE_DOWNLOAD_VIDEOS = "Download videos (when downloading playlists, albums, mixes)('0'-No,'1'-Yes):"
    CHANGE_ADD_LRC_FILE = "Dalszöveg mentése időbélyeggel .lrc fájl('0'-Nem,'1'-Igen):"
    CHANGE_MULITHREAD_DOWNLOAD = "Többszálas letöltés('0'-Nem,'1'-Igen):"
    CHANGE_USE_DOWNLOAD_DELAY = "Use Download Delay('0'-No,'1'-Yes):"

    # {} are required in these strings
    AUTH_START_LOGIN = "Bejelentkezési folyamat elindítása..."
    AUTH_NEXT_STEP = "Menj a {} a következő {} a beállítás befejezéséhez."
    AUTH_WAITING = "Engedélyre várva..."
    AUTH_TIMEOUT = "A művelet leállt."

    MSG_VALID_ACCESSTOKEN = "AccessToken érvényessége {}."
    MSG_INVALID_ACCESSTOKEN = "Lejárt AccessToken. Megpróbálom frissíteni."
    MSG_PATH_ERR = "Az útvonal hibás!"
    MSG_INPUT_ERR = "Beviteli hiba!"

    MODEL_ALBUM_PROPERTY = "ALBUM-INFÓ"
    MODEL_TRACK_PROPERTY = "TRACK-INFÓ"
    MODEL_VIDEO_PROPERTY = "VIDEO-INFÓ"
    MODEL_ARTIST_PROPERTY = "ELŐADÓ-INFÓ"
    MODEL_PLAYLIST_PROPERTY = "LEJÁTSZÁSI LISTA-INFÓ"

    MODEL_TITLE = 'Cím'
    MODEL_TRACK_NUMBER = 'Track száma'
    MODEL_VIDEO_NUMBER = 'Videó száma'
    MODEL_RELEASE_DATE = 'Megjelenés dátuma'
    MODEL_VERSION = 'Verzió'
    MODEL_EXPLICIT = 'Explicit'
    MODEL_ALBUM = 'Album'
    MODEL_ID = 'ID'
    MODEL_NAME = 'Név'
    MODEL_TYPE = 'Típus'
