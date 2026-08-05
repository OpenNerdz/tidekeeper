#!/usr/bin/env python
# -*- encoding: utf-8 -*-
'''
@File    :   settings.py
@Time    :   2020/11/08
@Author  :   Yaronzz
@Version :   3.0
@Contact :   yaronhuang@foxmail.com
@Desc    :
'''
import json
import aigpy
import base64
import logging
import os

from .lang.language import *
from .enums import *
from .environment import getDefaultDownloadPath


def getDefaultAudioQualityPriority():
    return [
        AudioQuality.Max,
        AudioQuality.HiFi,
        AudioQuality.High,
        AudioQuality.Normal,
    ]


class Settings(aigpy.model.ModelBase):
    checkExist = True
    includeEP = True
    saveCovers = True
    language = 0
    lyricFile = False
    apiKeyIndex = 4
    showProgress = True
    showTrackInfo = True
    saveAlbumInfo = False
    downloadVideos = True
    multiThread = False
    downloadDelay = True
    requestIntervalSeconds = 3.0
    adaptiveRateLimit = True
    saveAsFlac = False

    downloadPath = "./download/"
    audioQuality = AudioQuality.Max
    audioQualityPriority = []
    videoQuality = VideoQuality.P360
    usePlaylistFolder = True
    albumFolderFormat = R"{ArtistName}/{Flag} {AlbumTitle} [{AlbumID}] [{AlbumYear}]"
    playlistFolderFormat = R"Playlist/{PlaylistName} [{PlaylistUUID}]"
    trackFileFormat = R"{TrackNumber} - {ArtistName} - {TrackTitle}{ExplicitFlag}"
    videoFileFormat = R"{VideoNumber} - {ArtistName} - {VideoTitle}{ExplicitFlag}"

    def __init__(self):
        # ModelBase has no initializer; copy mutable defaults per instance.
        self.audioQualityPriority = list(type(self).audioQualityPriority)

    def getDefaultPathFormat(self, type: Type):
        if type == Type.Album:
            return R"{ArtistName}/{Flag} {AlbumTitle} [{AlbumID}] [{AlbumYear}]"
        elif type == Type.Playlist:
            return R"Playlist/{PlaylistName} [{PlaylistUUID}]"
        elif type == Type.Track:
            return R"{TrackNumber} - {ArtistName} - {TrackTitle}{ExplicitFlag}"
        elif type == Type.Video:
            return R"{VideoNumber} - {ArtistName} - {VideoTitle}{ExplicitFlag}"
        return ""

    def getAudioQualityOrNone(self, value):
        normalized = str(value).split("(", 1)[0].strip()
        alias = ''.join(ch for ch in normalized.lower() if ch.isalnum())
        aliases = {
            "aac96": AudioQuality.Normal,
            "low": AudioQuality.Normal,
            "lowest": AudioQuality.Normal,
            "normal": AudioQuality.Normal,
            "aac320": AudioQuality.High,
            "high": AudioQuality.High,
            "flac": AudioQuality.HiFi,
            "hifi": AudioQuality.HiFi,
            "lossless": AudioQuality.HiFi,
            "hires": AudioQuality.Master,
            "hireslossless": AudioQuality.Max,
            "dolbyatmos": AudioQuality.Atmos,
            "atmos": AudioQuality.Atmos,
        }
        if alias in aliases:
            return aliases[alias]
        for item in AudioQuality:
            if item == value:
                return item
            if item.name == normalized:
                return item
            if normalized.lower() == item.name.lower():
                return item
        return None

    def getAudioQuality(self, value):
        return self.getAudioQualityOrNone(value) or AudioQuality.Max

    def getAudioQualityPriority(self, value):
        if value is None:
            return []
        if isinstance(value, str):
            value = [item.strip() for item in value.split(',')]
        elif isinstance(value, AudioQuality):
            value = [value]

        priority = []
        for item in value:
            if item is None or str(item).strip() == "":
                continue
            quality = self.getAudioQualityOrNone(item)
            if quality is not None and quality not in priority:
                priority.append(quality)
        return priority

    def getDownloadAudioQualityPriority(self):
        priority = self.getAudioQualityPriority(self.audioQualityPriority)
        if priority:
            return priority
        return [self.audioQuality]

    def getVideoQuality(self, value):
        for item in VideoQuality:
            if item.name == value:
                return item
        return VideoQuality.P360

    def read(self, path):
        self._path_ = path
        txt = aigpy.file.getContent(self._path_)
        hasSavedSettings = len(txt) > 0
        if hasSavedSettings:
            try:
                data = json.loads(txt)
                if not isinstance(data, dict):
                    raise ValueError("settings root must be a JSON object")
                if aigpy.model.dictToModel(data, self) is None:
                    return
            except (json.JSONDecodeError, TypeError, ValueError) as error:
                logging.warning("Ignoring invalid settings file %s: %s", self._path_, error)
                hasSavedSettings = False

        self.audioQuality = self.getAudioQuality(self.audioQuality)
        self.audioQualityPriority = self.getAudioQualityPriority(self.audioQualityPriority)
        self.videoQuality = self.getVideoQuality(self.videoQuality)

        if self.albumFolderFormat is None:
            self.albumFolderFormat = self.getDefaultPathFormat(Type.Album)
        if self.trackFileFormat is None:
            self.trackFileFormat = self.getDefaultPathFormat(Type.Track)
        if self.playlistFolderFormat is None:
            self.playlistFolderFormat = self.getDefaultPathFormat(Type.Playlist)
        if self.videoFileFormat is None:
            self.videoFileFormat = self.getDefaultPathFormat(Type.Video)
        if self.apiKeyIndex is None:
            self.apiKeyIndex = 0
        if getattr(self, 'requestIntervalSeconds', None) is None:
            self.requestIntervalSeconds = 3.0
        else:
            self.requestIntervalSeconds = max(0.0, float(self.requestIntervalSeconds))
        if getattr(self, 'adaptiveRateLimit', None) is None:
            self.adaptiveRateLimit = True
        if getattr(self, 'saveAsFlac', None) is None:
            self.saveAsFlac = False
        if not hasSavedSettings:
            self.downloadPath = getDefaultDownloadPath()
            self.audioQuality = AudioQuality.Max
            self.audioQualityPriority = getDefaultAudioQualityPriority()

        LANG.setLang(self.language)
        syncPlaybackRateLimiter()

    def save(self):
        data = aigpy.model.modelToDict(self)
        data['audioQuality'] = self.audioQuality.name
        data['audioQualityPriority'] = [item.name for item in self.getAudioQualityPriority(self.audioQualityPriority)]
        data['videoQuality'] = self.videoQuality.name
        txt = json.dumps(data, indent=2, sort_keys=True)
        aigpy.file.write(self._path_, txt, 'w+')


class TokenSettings(aigpy.model.ModelBase):
    userid = None
    countryCode = None
    accessToken = None
    refreshToken = None
    expiresAfter = 0

    def __encode__(self, string):
        sw = bytes(string, 'utf-8')
        st = base64.b64encode(sw)
        return st

    def __decode__(self, string):
        try:
            sr = base64.b64decode(string)
            st = sr.decode()
            return st
        except (ValueError, UnicodeDecodeError):
            return string

    def read(self, path):
        self._path_ = path
        txt = aigpy.file.getContent(self._path_)
        if len(txt) > 0:
            try:
                data = json.loads(self.__decode__(txt))
                if not isinstance(data, dict):
                    raise ValueError("token root must be a JSON object")
                aigpy.model.dictToModel(data, self)
            except (json.JSONDecodeError, TypeError, ValueError) as error:
                logging.warning("Ignoring invalid token file %s: %s", self._path_, error)

    def __ensurePath__(self):
        if getattr(self, '_path_', None):
            return self._path_
        # Allow save() after programmatic login without a prior read().
        from .paths import PATHS
        self._path_ = PATHS.getTokenPath()
        return self._path_

    def save(self):
        path = self.__ensurePath__()
        data = aigpy.model.modelToDict(self)
        txt = json.dumps(data)
        encoded = self.__encode__(txt)
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, 'wb') as output:
                output.write(encoded)
        finally:
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass


def syncPlaybackRateLimiter():
    from .tidal import PLAYBACK_RATE_LIMITER

    if SETTINGS.downloadDelay is False:
        PLAYBACK_RATE_LIMITER.minInterval = 0.0
        return
    PLAYBACK_RATE_LIMITER.minInterval = max(0.0, float(getattr(SETTINGS, 'requestIntervalSeconds', 1.0) or 0.0))


# Singleton
SETTINGS = Settings()
TOKEN = TokenSettings()
