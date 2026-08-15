#!/usr/bin/env python
# -*- encoding: utf-8 -*-
'''
@File    :   korean.py
@Time    :   2021/11/24
@Author  :   jee019
@Version :   1.1
@Contact :   qwer010910@gmail.com
@Desc    :
'''

class LangKorean(object):
    SETTING = "설정"
    VALUE = "값"
    SETTING_DOWNLOAD_PATH = "다운로드 경로"
    SETTING_AUDIO_QUALITY = "음질"
    SETTING_VIDEO_QUALITY = "영상 화질"
    SETTING_CHECK_EXIST = "존재 유무 확인"
    SETTING_INCLUDE_EP = "싱글 및 EP 포함"
    SETTING_SAVE_COVERS = "커버 저장"
    SETTING_LANGUAGE = "언어"
    SETTING_USE_PLAYLIST_FOLDER = "재생목록 폴더 사용"
    SETTING_MULITHREAD_DOWNLOAD = "다중 스레드 다운로드"
    SETTING_ALBUM_FOLDER_FORMAT = "앨범 폴더 형식"
    SETTING_PLAYLIST_FOLDER_FORMAT = "Playlist folder format"
    SETTING_TRACK_FILE_FORMAT = "트랙 파일 형식"
    SETTING_VIDEO_FILE_FORMAT = "Video file format"
    SETTING_SHOW_PROGRESS = "진행 상태 표시"
    SETTING_SHOW_TRACKINFO = "트랙 정보 표시"
    SETTING_SAVE_ALBUMINFO = "AlbumInfo.txt 저장"
    SETTING_DOWNLOAD_VIDEOS = "Download videos"
    SETTING_ADD_LRC_FILE = "timed 가사 저장 (.lrc 파일)"
    SETTING_PATH = "설정 경로"
    SETTING_APIKEY = "APIKey support"
    SETTING_DOWNLOAD_DELAY = "Use Download Delay"

    PRINT_ERR = "[에러]"
    PRINT_INFO = "[정보]"
    PRINT_SUCCESS = "[성공]"

    PRINT_LATEST_VERSION = "최신 버전:"

    CHANGE_DOWNLOAD_PATH = "다운로드 경로('0'-변경 안 함):"
    CHANGE_AUDIO_QUALITY = "음질('0'-보통,'1'-높음,'2'-HiFi,'3'-Master,'4'-Max):"
    CHANGE_VIDEO_QUALITY = "영상 화질(1080, 720, 480, 360):"
    CHANGE_CHECK_EXIST = "다운로드 트랙 전에 존재하는 파일 확인('0'-아니요,'1'-예):"
    CHANGE_INCLUDE_EP = "아티스트 앨범 다운로드시 싱글 및 EP 포함('0'-아니요,'1'-예):"
    CHANGE_SAVE_COVERS = "커버 저장('0'-아니요,'1'-예):"
    CHANGE_LANGUAGE = "언어 선택"
    CHANGE_ALBUM_FOLDER_FORMAT = "앨범 폴더 형식('0'-변경 안 함,'default'-기본 설정):"
    CHANGE_PLAYLIST_FOLDER_FORMAT = "Playlist folder format('0'-not modify,'default'-to set default):"
    CHANGE_TRACK_FILE_FORMAT = "트랙 파일 형식('0'-변경 안 함,'default'-기본 설정):"
    CHANGE_VIDEO_FILE_FORMAT = "Video file format('0'-not modify,'default'-to set default):"
    CHANGE_SHOW_PROGRESS = "진행 상태 표시('0'-아니요,'1'-예):"
    CHANGE_SHOW_TRACKINFO = "트랙 정보 표시('0'-아니요,'1'-예):"
    CHANGE_SAVE_ALBUM_INFO = "AlbumInfo.txt 저장('0'-아니요,'1'-예):"
    CHANGE_DOWNLOAD_VIDEOS = "Download videos (when downloading playlists, albums, mixes)('0'-No,'1'-Yes):"
    CHANGE_ADD_LRC_FILE = "timed 가사 .lrc 파일 저장 ('0'-아니요,'1'-예):"
    CHANGE_MULITHREAD_DOWNLOAD = "Multi thread download('0'-No,'1'-Yes):"
    CHANGE_USE_DOWNLOAD_DELAY = "Use Download Delay('0'-No,'1'-Yes):"

    # {} are required in these strings
    AUTH_START_LOGIN = "로그인 중..."
    AUTH_NEXT_STEP = "설치를 완료하려면 {}로 이동하십시오. 다음 {} 내에 있습니다."
    AUTH_WAITING = "승인 대기 중..."
    AUTH_TIMEOUT = "작업 시간 초과"

    MSG_VALID_ACCESSTOKEN = "{}에 대해 액세스 토큰이 유효합니다."
    MSG_INVALID_ACCESSTOKEN = "만료된 액세스 토큰입니다. 새로 고침 중입니다."
    MSG_PATH_ERR = "경로 오류!"
    MSG_INPUT_ERR = "입력 오류!"

    MODEL_ALBUM_PROPERTY = "앨범-정보"
    MODEL_TRACK_PROPERTY = "트랙-정보"
    MODEL_VIDEO_PROPERTY = "영상-정보"
    MODEL_ARTIST_PROPERTY = "아티스트-정보"
    MODEL_PLAYLIST_PROPERTY = "재생목록-정보"

    MODEL_TITLE = '제목'
    MODEL_TRACK_NUMBER = '트랙 넘버'
    MODEL_VIDEO_NUMBER = '영상 넘버'
    MODEL_RELEASE_DATE = '발매일'
    MODEL_VERSION = '버전'
    MODEL_EXPLICIT = 'Explicit'
    MODEL_ALBUM = '앨범'
    MODEL_ID = '아이디'
    MODEL_NAME = '이름'
    MODEL_TYPE = '형식'
