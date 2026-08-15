#!/usr/bin/env python
# -*- encoding: utf-8 -*-
'''
@File    :   turkish.py
@Time    :   2020/09/13
@Author  :   Gorgeous & shhade for hack & Mutlu ŞEN
@Version :   1.0
@Contact :   realmutlusen@gmail.com
@Desc    :   Yanlış çeviri ya da düzenleme için 'realmutlusen@gmail.com'a mail atabilirsiniz.
'''

class LangTurkish(object):
    SETTING = "AYARLAR"
    VALUE = "VERİLER"
    SETTING_DOWNLOAD_PATH = "İndirme konumu:"
    SETTING_AUDIO_QUALITY = "Ses kalitesi:"
    SETTING_VIDEO_QUALITY = "Video kalitesi:"
    SETTING_CHECK_EXIST = "İndirilmiş mi diye kontrol edilsin:"
    SETTING_INCLUDE_EP = "Single'leri ve EP'leri dahil edisin:"
    SETTING_SAVE_COVERS = "Albüm kapağı indirilsin:"
    SETTING_LANGUAGE = "Kullanılan lisan:"
    SETTING_USE_PLAYLIST_FOLDER = "Albümler klasör halinde indirilsin mi ?"
    SETTING_MULITHREAD_DOWNLOAD = "Şarkılar tek tek indirilsin mi?"
    SETTING_ALBUM_FOLDER_FORMAT = "Klasör ismi formatı:"
    SETTING_PLAYLIST_FOLDER_FORMAT = "Playlist folder format"
    SETTING_TRACK_FILE_FORMAT = "Dosya ismi formatı:"
    SETTING_VIDEO_FILE_FORMAT = "Video file format"
    SETTING_SHOW_PROGRESS = "İndirme Çubuğu Görüntüleme:"
    SETTING_SHOW_TRACKINFO = "Show Track Info"
    SETTING_SAVE_ALBUMINFO = "Save AlbumInfo.txt"
    SETTING_DOWNLOAD_VIDEOS = "Download videos"
    SETTING_ADD_LRC_FILE = "Save timed lyrics (.lrc file)"
    SETTING_PATH = "Settings path"
    SETTING_APIKEY = "APIKey support"
    SETTING_DOWNLOAD_DELAY = "Use Download Delay"

    PRINT_ERR = "[HATA OLUŞTU]"
    PRINT_INFO = "[BİLGİ]"
    PRINT_SUCCESS = "[İNDİRİLDİ]"

    PRINT_LATEST_VERSION = "Güncelleme Mevcut:"

    CHANGE_DOWNLOAD_PATH = ">>> İndirme Konumu ('0' aynı kalsın): "
    CHANGE_AUDIO_QUALITY = ">>> Ses Kalitesi ('0'-Normal,'1'-Yüksek,'2'-HiFi,'3'-[M]aster,'4'-Max): "
    CHANGE_VIDEO_QUALITY = ">>> Video Kalitesi (1080, 720, 480, 360): "
    CHANGE_CHECK_EXIST = ">>> Dosya daha önce indirilmiş mi diye kontrol edilsin mi ?('0'-Hayır,'1'-Evet): "
    CHANGE_INCLUDE_EP = ">>> Artist'in tüm albümlerini indirirken Single'leri ve EP'leri de dahil edilsin mi ?('0'-Hayır,'1'-Evet): "
    CHANGE_SAVE_COVERS = ">>> Albüm kapağı indirilsin mi?('0'-Hayır,'1'-Evet): "
    CHANGE_LANGUAGE = ">>> Lisan Seç "
    CHANGE_ALBUM_FOLDER_FORMAT = "Albüm Klasör İsmi Formatı('0' aynı kalsın):"
    CHANGE_PLAYLIST_FOLDER_FORMAT = "Playlist folder format('0'-not modify,'default'-to set default):"
    CHANGE_TRACK_FILE_FORMAT = "Dosya İsmi Formatı('0' aynı kalsın):"
    CHANGE_VIDEO_FILE_FORMAT = "Video file format('0'-not modify,'default'-to set default):"
    CHANGE_SHOW_PROGRESS = "İndirme Çubuğu Görüntülensin mi?('0'-Hayır,'1'-Evet):"
    CHANGE_SHOW_TRACKINFO = "Show track info('0'-No,'1'-Yes):"
    CHANGE_SAVE_ALBUM_INFO = "Save AlbumInfo.txt('0'-No,'1'-Yes):"
    CHANGE_DOWNLOAD_VIDEOS = "Download videos (when downloading playlists, albums, mixes)('0'-No,'1'-Yes):"
    CHANGE_ADD_LRC_FILE = "Save timed lyrics .lrc file ('0'-No,'1'-Yes):"
    CHANGE_MULITHREAD_DOWNLOAD = "Multi thread download('0'-No,'1'-Yes):"
    CHANGE_USE_DOWNLOAD_DELAY = "Use Download Delay('0'-No,'1'-Yes):"

    # {} are required in these strings
    AUTH_START_LOGIN = "Giriş işlemleri başlatıldı..."
    AUTH_NEXT_STEP = "Bu siteden {} hesabınıza giriş yapınız ve üstteki kodu giriniz. ({} dakikanız var.)"
    AUTH_WAITING = "İşlemleri tamamlamanız bekleniyor..."
    AUTH_TIMEOUT = "Lütfen size verilen süre içerisinde işlemleriniz tamamlayınız."

    MSG_VALID_ACCESSTOKEN = "AccessToken good for {}."
    MSG_INVALID_ACCESSTOKEN = "Expired AccessToken. Attempting to refresh it."
    MSG_PATH_ERR = "İndirme konumu ile alakalı bir sorun var! ('/storage/emulated/0/Download/' şeklinde girebilirsiniz.)"
    MSG_INPUT_ERR = "Giriş Hatalı!"

    MODEL_ALBUM_PROPERTY = "ALBÜM-BİLGİLERİ"
    MODEL_TRACK_PROPERTY = "ŞARKI-BİLGİLERİ"
    MODEL_VIDEO_PROPERTY = "VİDEO-BİLGİLERİ"
    MODEL_ARTIST_PROPERTY = "ARTİST-BİLGİLERİ"
    MODEL_PLAYLIST_PROPERTY = "OYNATMA LİSTESİ-BİLGİLERİ"

    MODEL_TITLE = 'Şarkı/Albüm Adı:'
    MODEL_TRACK_NUMBER = 'Şarkı Sayısı'
    MODEL_VIDEO_NUMBER = 'Video Sayısı'
    MODEL_RELEASE_DATE = 'Çıkış Yılı:'
    MODEL_VERSION = 'Versiyon'
    MODEL_EXPLICIT = 'Küfürlü'
    MODEL_ALBUM = 'Albüm'
    MODEL_ID = 'ID'
    MODEL_NAME = 'İsim'
    MODEL_TYPE = 'Türü'
