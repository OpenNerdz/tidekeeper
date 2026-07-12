#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
@File    :  paths.py
@Date    :  2022/06/10
@Author  :  Yaronzz
@Version :  1.0
@Contact :  yaronhuang@foxmail.com
@Desc    :
"""
import os
import subprocess
import sys
import aigpy
import datetime

from .tidal import *
from .settings import *


def __fixPath__(name: str):
    return aigpy.path.replaceLimitChar(name, '-').strip()


def __getYear__(releaseDate: str):
    if releaseDate is None or releaseDate == '':
        return ''
    return aigpy.string.getSubOnlyEnd(releaseDate, '-')


def __getDurationStr__(seconds):
    time_string = str(datetime.timedelta(seconds=seconds))
    if time_string.startswith('0:'):
        time_string = time_string[2:]
    return time_string


def __getExtension__(stream: StreamUrl):
    container = (stream.container or '').lower()
    manifestMimeType = (stream.manifestMimeType or '').lower()
    codec = (stream.codec or '').lower()

    if SETTINGS.saveAsFlac and 'flac' in codec:
        return '.flac'

    if 'dash+xml' in manifestMimeType or 'mp4' in container:
        return '.m4a'

    if '.flac' in stream.url:
        return '.flac'
    if '.mp4' in stream.url:
        return '.m4a'
    return '.m4a'


def __getStreamQuality__(stream: StreamUrl):
    quality = (getattr(stream, 'soundQuality', None) or '').strip()
    labels = {
        'DOLBY_ATMOS': 'Dolby Atmos',
        'HI_RES_LOSSLESS': 'Max',
        'HI_RES': 'Master',
        'LOSSLESS': 'HiFi',
        'HIGH': 'High',
        'LOW': 'Normal',
    }
    if quality in labels:
        return labels[quality]
    return quality.replace('_', ' ').title() if quality else ''


def __isAtmosStream__(stream: StreamUrl):
    return (getattr(stream, 'soundQuality', None) or '').upper() == 'DOLBY_ATMOS'


def __hasStreamIdentifierToken__(pathFormat: str):
    return '{StreamQuality}' in pathFormat or '{Codec}' in pathFormat


def getAlbumPath(album):
    artistID = __fixPath__(TIDAL_API.getArtistsID(album.artists))
    artistName = __fixPath__(TIDAL_API.getArtistsName(album.artists))
    albumArtistName = __fixPath__(album.artist.name) if album.artist is not None else ""

    # album folder pre: [ME]
    flag = TIDAL_API.getFlag(album, Type.Album, True, "")
    if SETTINGS.audioQuality != AudioQuality.Master and SETTINGS.audioQuality != AudioQuality.Max:
        flag = flag.replace("M", "")
    if flag != "":
        flag = "[" + flag + "] "

    # album and addyear
    albumName = __fixPath__(album.title)
    year = __getYear__(album.releaseDate)

    # retpath
    retpath = SETTINGS.albumFolderFormat
    if retpath is None or len(retpath) <= 0:
        retpath = SETTINGS.getDefaultPathFormat(Type.Album)
    retpath = retpath.replace(R"{ArtistID}", artistID)
    retpath = retpath.replace(R"{ArtistName}", artistName)
    retpath = retpath.replace(R"{AlbumArtistName}", albumArtistName)
    retpath = retpath.replace(R"{Flag}", flag)
    retpath = retpath.replace(R"{AlbumID}", str(album.id))
    retpath = retpath.replace(R"{AlbumYear}", year)
    retpath = retpath.replace(R"{AlbumTitle}", albumName)
    retpath = retpath.replace(R"{AudioQuality}", album.audioQuality)
    retpath = retpath.replace(R"{DurationSeconds}", str(album.duration))
    retpath = retpath.replace(R"{Duration}", __getDurationStr__(album.duration))
    retpath = retpath.replace(R"{NumberOfTracks}", str(album.numberOfTracks))
    retpath = retpath.replace(R"{NumberOfVideos}", str(album.numberOfVideos))
    retpath = retpath.replace(R"{NumberOfVolumes}", str(album.numberOfVolumes))
    retpath = retpath.replace(R"{ReleaseDate}", str(album.releaseDate))
    retpath = retpath.replace(R"{RecordType}", album.type)
    retpath = retpath.replace(R"{None}", "")
    retpath = retpath.strip()
    return f"{SETTINGS.downloadPath}/{retpath}"

def getPlaylistPath(playlist):
    playlistName = __fixPath__(playlist.title)

    # retpath
    retpath = SETTINGS.playlistFolderFormat
    if retpath is None or len(retpath) <= 0:
        retpath = SETTINGS.getDefaultPathFormat(Type.Playlist)
    retpath = retpath.replace(R"{PlaylistUUID}", str(playlist.uuid))
    retpath = retpath.replace(R"{PlaylistName}", playlistName)
    return f"{SETTINGS.downloadPath}/{retpath}"


def getTrackPath(track, stream, album=None, playlist=None):
    base = './'
    number = str(track.trackNumber).rjust(2, '0')
    if album is not None:
        base = getAlbumPath(album)
        if album.numberOfVolumes > 1:
            base += f'/CD{str(track.volumeNumber)}'

    if playlist is not None and SETTINGS.usePlaylistFolder:
        base = getPlaylistPath(playlist)
        number = str(track.trackNumberOnPlaylist).rjust(2, '0')

    # artist
    artists = __fixPath__(TIDAL_API.getArtistsName(track.artists))
    artist = __fixPath__(track.artist.name) if track.artist is not None else ""

    # title
    title = __fixPath__(track.title)
    if not aigpy.string.isNull(track.version):
        title += f' ({__fixPath__(track.version)})'

    # explicit
    explicit = "(Explicit)" if track.explicit else ''

    # album and addyear
    albumName = __fixPath__(album.title) if album is not None else ''
    year = __getYear__(album.releaseDate) if album is not None else ''

    # extension
    extension = __getExtension__(stream)

    retpath = SETTINGS.trackFileFormat
    if retpath is None or len(retpath) <= 0:
        retpath = SETTINGS.getDefaultPathFormat(Type.Track)
    hasStreamIdentifier = __hasStreamIdentifierToken__(retpath)
    retpath = retpath.replace(R"{TrackNumber}", number)
    retpath = retpath.replace(R"{ArtistName}", artist)
    retpath = retpath.replace(R"{ArtistsName}", artists)
    retpath = retpath.replace(R"{TrackTitle}", title)
    retpath = retpath.replace(R"{ExplicitFlag}", explicit)
    retpath = retpath.replace(R"{AlbumYear}", year)
    retpath = retpath.replace(R"{AlbumTitle}", albumName)
    retpath = retpath.replace(R"{AudioQuality}", track.audioQuality)
    retpath = retpath.replace(R"{StreamQuality}", __fixPath__(__getStreamQuality__(stream)))
    retpath = retpath.replace(R"{Codec}", __fixPath__(stream.codec or ''))
    retpath = retpath.replace(R"{DurationSeconds}", str(track.duration))
    retpath = retpath.replace(R"{Duration}", __getDurationStr__(track.duration))
    retpath = retpath.replace(R"{TrackID}", str(track.id))
    retpath = retpath.strip()
    if __isAtmosStream__(stream) and SETTINGS.audioQuality == AudioQuality.Atmos and not hasStreamIdentifier:
        retpath += " [Dolby Atmos]"
    return f"{base}/{retpath}{extension}"


def getVideoPath(video, album=None, playlist=None):
    base = SETTINGS.downloadPath + '/Video/'
    if album is not None and album.title is not None:
        base = getAlbumPath(album)
    elif playlist is not None and SETTINGS.usePlaylistFolder:
        base = getPlaylistPath(playlist)

    # get number
    number = str(video.trackNumber).rjust(2, '0')

    # get artist
    artists = __fixPath__(TIDAL_API.getArtistsName(video.artists))
    artist = __fixPath__(video.artist.name) if video.artist is not None else ""

    # explicit
    explicit = "(Explicit)" if video.explicit else ''

    # title and year and extension
    title = __fixPath__(video.title)
    year = __getYear__(video.releaseDate)
    extension = ".mp4"

    retpath = SETTINGS.videoFileFormat
    if retpath is None or len(retpath) <= 0:
        retpath = SETTINGS.getDefaultPathFormat(Type.Video)
    retpath = retpath.replace(R"{VideoNumber}", number)
    retpath = retpath.replace(R"{ArtistName}", artist)
    retpath = retpath.replace(R"{ArtistsName}", artists)
    retpath = retpath.replace(R"{VideoTitle}", title)
    retpath = retpath.replace(R"{ExplicitFlag}", explicit)
    retpath = retpath.replace(R"{VideoYear}", year)
    retpath = retpath.replace(R"{VideoID}", str(video.id))
    retpath = retpath.strip()
    return f"{base}/{retpath}{extension}"

def openPath(path):
    target = os.path.abspath(os.path.expanduser(path or SETTINGS.downloadPath))
    if os.path.isfile(target):
        target = os.path.dirname(target)
    os.makedirs(target, exist_ok=True)

    if sys.platform.startswith("win"):
        os.startfile(target)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", target])
    else:
        subprocess.Popen(["xdg-open", target])
    return target

class Paths(aigpy.model.ModelBase):
    homePathOverride = None

    def __getHomePath__(self):
        if self.homePathOverride == None:
            return self.__getDefaultHomePath__()
        else:
            return self.homePathOverride

    def __getDefaultHomePath__(self):
        if "XDG_CONFIG_HOME" in os.environ:
            return os.environ['XDG_CONFIG_HOME']
        elif "HOME" in os.environ:
            return os.environ['HOME']
        elif "HOMEDRIVE" in os.environ and "HOMEPATH" in os.environ:
            return os.environ['HOMEDRIVE'] + os.environ['HOMEPATH']
        else:
            return os.path.abspath("./")

    def getLogPath(self):
        return self.__getHomePath__() + '/.tidal-dl.log'

    def getTokenPath(self):
        return self.__getHomePath__() + '/.tidal-dl.token.json'

    def getProfilePath(self):
        return self.__getHomePath__() + '/.tidal-dl.json'


    def getConfigDirectory(self):
        return os.path.dirname(self.getProfilePath()) or os.path.abspath("./")


    def getPathSummary(self):
        return [
            ("Download path", SETTINGS.downloadPath),
            ("Config folder", self.getConfigDirectory()),
            ("Settings file", self.getProfilePath()),
            ("Token file", self.getTokenPath()),
            ("Log file", self.getLogPath()),
        ]

# Singleton
PATHS = Paths()
