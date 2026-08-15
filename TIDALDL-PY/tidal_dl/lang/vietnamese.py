#!/usr/bin/env python
# -*- encoding: utf-8 -*-
'''
@File    :   vietnamese.py
@Time    :   2022/2/9
@Author  :   MinhNgo, CDzungx
@Version :   1.0
@Contact :   iam.minhnc@outlook.com
@Desc    :
'''

class LangVietnamese(object):
    SETTING = "THIẾT LẬP"
    VALUE = "GIÁ TRỊ"
    SETTING_DOWNLOAD_PATH = "Đường dẫn tải về"
    SETTING_AUDIO_QUALITY = "Chất lượng âm thanh"
    SETTING_VIDEO_QUALITY = "Chất lượng video"
    SETTING_CHECK_EXIST = "Kiểm tra tồn tại"
    SETTING_INCLUDE_EP = "Bao gồm đĩa đơn & ep"
    SETTING_SAVE_COVERS = "Tải ảnh bìa"
    SETTING_LANGUAGE = "Ngôn ngữ"
    SETTING_USE_PLAYLIST_FOLDER = "Thư mục cho danh sách phát"
    SETTING_MULITHREAD_DOWNLOAD = "Tải về đa luồng"
    SETTING_ALBUM_FOLDER_FORMAT = "Định dạng thư mục album"
    SETTING_PLAYLIST_FOLDER_FORMAT = "Playlist folder format"
    SETTING_TRACK_FILE_FORMAT = "Định dạng tên tệp nhạc"
    SETTING_VIDEO_FILE_FORMAT = "Video file format"
    SETTING_SHOW_PROGRESS = "Hiện tiến trình"
    SETTING_SHOW_TRACKINFO = "Hiện thông tin bài"
    SETTING_SAVE_ALBUMINFO = "Lưu AlbumInfo.txt"
    SETTING_DOWNLOAD_VIDEOS = "Download videos"
    SETTING_ADD_LRC_FILE = "Lưu timed lyrics (tệp .lrc)"
    SETTING_PATH = "Đường dẫn cài đặt"
    SETTING_APIKEY = "Hỗ trợ APIKey"
    SETTING_DOWNLOAD_DELAY = "Use Download Delay"

    PRINT_ERR = "[LỖI]"
    PRINT_INFO = "[THÔNG TIN]"
    PRINT_SUCCESS = "[XONG]"

    PRINT_LATEST_VERSION = "Bản mới nhất:"

    CHANGE_DOWNLOAD_PATH = "Đường dẫn tải về('0' không đổi):"
    CHANGE_AUDIO_QUALITY = "Chất lượng âm thanh('0'-Normal,'1'-High,'2'-HiFi,'3'-Master,'4'-Max):"
    CHANGE_VIDEO_QUALITY = "Chất lượng video(1080, 720, 480, 360):"
    CHANGE_CHECK_EXIST = "Kiểm tra tệp đã tồn tại chưa trước khi tải('0'-Không,'1'-Có):"
    CHANGE_INCLUDE_EP = "Bao gồm đĩa đơn và EPs khi tải tất cả nhạc của nghệ sĩ('0'-Không,'1'-Có):"
    CHANGE_SAVE_COVERS = "Tải ảnh bìa('0'-Không,'1'-Có):"
    CHANGE_LANGUAGE = "Chọn ngôn ngữ"
    CHANGE_ALBUM_FOLDER_FORMAT = "Định dạng thư mục album('0' không đổi,'default' để đặt về mặc định):"
    CHANGE_PLAYLIST_FOLDER_FORMAT = "Playlist folder format('0'-not modify,'default'-to set default):"
    CHANGE_TRACK_FILE_FORMAT = "Định dạng tên tệp nhạc('0' không đổi,'default' để đặt về mặc định):"
    CHANGE_VIDEO_FILE_FORMAT = "Video file format('0'-not modify,'default'-to set default):"
    CHANGE_SHOW_PROGRESS = "Hiện tiến trình('0'-Không,'1'-Có):"
    CHANGE_SHOW_TRACKINFO = "Hiện thông tin bài('0'-Không,'1'-Có):"
    CHANGE_SAVE_ALBUM_INFO = "Lưu AlbumInfo.txt('0'-Không,'1'-Có):"
    CHANGE_DOWNLOAD_VIDEOS = "Download videos (when downloading playlists, albums, mixes)('0'-No,'1'-Yes):"
    CHANGE_ADD_LRC_FILE = "Lưu timed lyrics tệp .lrc ('0'-Không,'1'-Có):"
    CHANGE_MULITHREAD_DOWNLOAD = "Multi thread download('0'-No,'1'-Yes):"
    CHANGE_USE_DOWNLOAD_DELAY = "Use Download Delay('0'-No,'1'-Yes):"

    # {} are required in these strings
    AUTH_START_LOGIN = "Đang bắt đầu đăng nhập..."
    AUTH_NEXT_STEP = "Vào trang {} trong vòng {} để hoàn tất thiết lập."
    AUTH_WAITING = "Đang chờ xác minh..."
    AUTH_TIMEOUT = "Đã vượt quá thời gian chờ."

    MSG_VALID_ACCESSTOKEN = "AccessToken vẫn tốt trong {}."
    MSG_INVALID_ACCESSTOKEN = "AccessToken hết hạn. Đang cố làm mới."
    MSG_PATH_ERR = "Lỗi đường dẫn!"
    MSG_INPUT_ERR = "Lỗi nhập!"

    MODEL_ALBUM_PROPERTY = "THÔNG-TIN-ALBUM"
    MODEL_TRACK_PROPERTY = "THÔNG-TIN-BÀI"
    MODEL_VIDEO_PROPERTY = "THÔNG-TIN-VIDEO"
    MODEL_ARTIST_PROPERTY = "THÔNG-TIN-NGHỆ-SĨ"
    MODEL_PLAYLIST_PROPERTY = "THÔNG-TIN-DANH-SÁCH-PHÁT"

    MODEL_TITLE = 'Tựa Đề'
    MODEL_TRACK_NUMBER = 'Số Bài'
    MODEL_VIDEO_NUMBER = 'Số Video'
    MODEL_RELEASE_DATE = 'Ngày Phát Hành'
    MODEL_VERSION = 'Phiên Bản'
    MODEL_EXPLICIT = 'Explicit'
    MODEL_ALBUM = 'Album'
    MODEL_ID = 'ID'
    MODEL_NAME = 'Tên'
    MODEL_TYPE = 'Loại'
