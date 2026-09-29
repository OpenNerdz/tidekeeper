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
import hashlib
import re
import unicodedata

from .enums import SOUND_QUALITIES, AudioQuality, Type, audio_quality_label
from .model import StreamUrl
from .tidal import TIDAL_API
from .settings import SETTINGS


WINDOWS_RESERVED_NAMES = {
    'CON', 'PRN', 'AUX', 'NUL',
    *(f'COM{number}' for number in range(1, 10)),
    *(f'LPT{number}' for number in range(1, 10)),
}
MAX_COMPONENT_BYTES = 240
# Leave room for extensions, receipts, and nested processing/remux suffixes
# (including two process IDs) on filesystems with a 255-byte component limit.
MAX_MEDIA_STEM_BYTES = 200


def downloadRoot():
    """The configured download folder with ``~`` expanded, as used for every write."""
    return os.path.expanduser(SETTINGS.downloadPath or '.')


def legacyDownloadFolder():
    """A folder literally named ``~`` left by releases before 2026.9.29.0, if any.

    Those releases did not expand ``~`` for album, playlist, and video paths, so a
    folder such as ``~/Music`` was created inside the working directory instead.
    """
    configured = SETTINGS.downloadPath or ''
    if not configured.startswith('~'):
        return None
    literal = os.path.abspath(configured)
    if literal == os.path.abspath(downloadRoot()) or not os.path.isdir(literal):
        return None
    return literal


def legacyDownloadNotice():
    """Tell the user where earlier downloads went, so they are not fetched again."""
    folder = legacyDownloadFolder()
    if folder is None:
        return None
    return (f"Downloads from earlier versions are in {folder}. Move them into {downloadRoot()} "
            "so Tidekeeper recognizes them instead of downloading them again.")


def _truncateComponent(value, original, max_bytes=MAX_COMPONENT_BYTES):
    encoded = value.encode('utf-8')
    if len(encoded) <= max_bytes:
        return value
    suffix = '-' + hashlib.sha256(original.encode('utf-8')).hexdigest()[:10]
    budget = max_bytes - len(suffix.encode('ascii'))
    clipped = encoded[:budget]
    while clipped:
        try:
            return clipped.decode('utf-8').rstrip(' .') + suffix
        except UnicodeDecodeError as error:
            clipped = clipped[:error.start]
    return '_' + suffix


def _fixPath(name: str):
    """Return one portable, non-empty filesystem component."""
    original = unicodedata.normalize('NFC', str(name or ''))
    if not original:
        return ''
    value = ''.join('-' if unicodedata.category(char).startswith('C') else char for char in original)
    value = re.sub(r'[<>:"/\\|?*]+', '-', value)
    value = re.sub(r'\s+', ' ', value).strip().rstrip(' .')
    if value in ('', '.', '..'):
        value = '_'
    stem = value.split('.', 1)[0].upper()
    if stem in WINDOWS_RESERVED_NAMES:
        value = '_' + value
    return _truncateComponent(value, original)


def _safeTemplatePath(path):
    # Templates intentionally use '/' for subfolders on every platform. Treat
    # backslashes as separators too, then sanitize every component so '..', an
    # absolute path, controls, or Windows device names cannot escape the chosen
    # download directory.
    parts = re.split(r'[/\\]+', str(path or ''))
    return '/'.join(_fixPath(part) for part in parts if part not in ('', '.', '..')) or '_'


def _safeMediaPath(path, extension):
    directory, separator, stem = _safeTemplatePath(path).rpartition('/')
    stem = _truncateComponent(stem, stem, MAX_MEDIA_STEM_BYTES)
    return directory + separator + stem + extension


def _getYear(releaseDate: str):
    if releaseDate is None or releaseDate == '':
        return ''
    return aigpy.string.getSubOnlyEnd(releaseDate, '-')


def _getDurationStr(seconds):
    time_string = str(datetime.timedelta(seconds=seconds))
    if time_string.startswith('0:'):
        time_string = time_string[2:]
    return time_string


def _getExtension(stream: StreamUrl):
    container = (stream.container or '').lower()
    manifestMimeType = (stream.manifestMimeType or '').lower()
    codec = (stream.codec or '').lower()

    if SETTINGS.saveAsFlac and 'flac' in codec:
        return '.flac'

    if 'dash+xml' in manifestMimeType or 'mp4' in container:
        return '.m4a'

    if '.flac' in (stream.url or ''):
        return '.flac'
    return '.m4a'


def _getStreamQuality(stream: StreamUrl):
    quality = (getattr(stream, 'soundQuality', None) or '').strip()
    if quality in SOUND_QUALITIES:
        return audio_quality_label(SOUND_QUALITIES[quality])
    return quality.replace('_', ' ').title() if quality else ''


def _isAtmosStream(stream: StreamUrl):
    return (getattr(stream, 'soundQuality', None) or '').upper() == 'DOLBY_ATMOS'


def _hasStreamIdentifierToken(pathFormat: str):
    return '{StreamQuality}' in pathFormat or '{Codec}' in pathFormat


def _tokenValue(value):
    if value is None:
        return ""
    return str(value)


def getAlbumPath(album):
    artistID = _fixPath(TIDAL_API.getArtistsID(album.artists))
    artistName = _fixPath(TIDAL_API.getArtistsName(album.artists))
    primary_artist = getattr(album, 'artist', None)
    albumArtistID = _fixPath(_tokenValue(getattr(primary_artist, 'id', None)))
    albumArtistName = _fixPath(_tokenValue(getattr(primary_artist, 'name', None)))

    # album folder pre: [ME]
    flag = TIDAL_API.getFlag(album, Type.Album, True, "")
    if SETTINGS.audioQuality != AudioQuality.Master and SETTINGS.audioQuality != AudioQuality.Max:
        flag = flag.replace("M", "")
    if flag != "":
        flag = "[" + flag + "] "

    # album and addyear
    albumName = _fixPath(album.title)
    year = _getYear(album.releaseDate)

    # retpath
    retpath = SETTINGS.albumFolderFormat
    if retpath is None or len(retpath) <= 0:
        retpath = SETTINGS.getDefaultPathFormat(Type.Album)
    retpath = retpath.replace(R"{ArtistID}", artistID)
    retpath = retpath.replace(R"{ArtistName}", artistName)
    retpath = retpath.replace(R"{AlbumArtistID}", albumArtistID)
    retpath = retpath.replace(R"{AlbumArtistName}", albumArtistName)
    retpath = retpath.replace(R"{Flag}", flag)
    retpath = retpath.replace(R"{AlbumID}", _tokenValue(album.id))
    retpath = retpath.replace(R"{AlbumYear}", year)
    retpath = retpath.replace(R"{AlbumTitle}", albumName)
    retpath = retpath.replace(R"{AudioQuality}", _tokenValue(album.audioQuality))
    retpath = retpath.replace(R"{DurationSeconds}", _tokenValue(album.duration or 0))
    retpath = retpath.replace(R"{Duration}", _fixPath(_getDurationStr(album.duration or 0)))
    retpath = retpath.replace(R"{NumberOfTracks}", _tokenValue(album.numberOfTracks or 0))
    retpath = retpath.replace(R"{NumberOfVideos}", _tokenValue(album.numberOfVideos or 0))
    retpath = retpath.replace(R"{NumberOfVolumes}", _tokenValue(album.numberOfVolumes or 0))
    retpath = retpath.replace(R"{ReleaseDate}", _fixPath(_tokenValue(album.releaseDate)))
    retpath = retpath.replace(R"{RecordType}", _tokenValue(album.type))
    retpath = retpath.replace(R"{None}", "")
    return f"{downloadRoot()}/{_safeTemplatePath(retpath.strip())}"


def getPlaylistPath(playlist):
    playlistName = _fixPath(playlist.title)

    # retpath
    retpath = SETTINGS.playlistFolderFormat
    if retpath is None or len(retpath) <= 0:
        retpath = SETTINGS.getDefaultPathFormat(Type.Playlist)
    retpath = retpath.replace(R"{PlaylistUUID}", str(playlist.uuid))
    retpath = retpath.replace(R"{PlaylistName}", playlistName)
    return f"{downloadRoot()}/{_safeTemplatePath(retpath)}"


def getTrackPath(track, stream, album=None, playlist=None):
    base = os.path.normpath(downloadRoot())
    number = str(track.trackNumber).rjust(2, '0')
    if album is not None:
        base = getAlbumPath(album)
        if int(getattr(album, 'numberOfVolumes', 0) or 0) > 1:
            base += '/CD' + _fixPath(str(track.volumeNumber or 1))

    if playlist is not None and SETTINGS.usePlaylistFolder:
        base = getPlaylistPath(playlist)
        number = str(track.trackNumberOnPlaylist).rjust(2, '0')

    # artist
    artists = _fixPath(TIDAL_API.getArtistsName(track.artists))
    artistID = _fixPath(TIDAL_API.getArtistsID(track.artists))
    primary_artist = getattr(track, 'artist', None)
    trackArtistID = _fixPath(_tokenValue(getattr(primary_artist, 'id', None)))
    trackArtistName = _fixPath(_tokenValue(getattr(primary_artist, 'name', None)))

    # title
    title = _fixPath(track.title)
    if not aigpy.string.isNull(track.version):
        title += f' ({_fixPath(track.version)})'

    # explicit
    explicit = "(Explicit)" if track.explicit else ''

    # album and addyear
    albumName = _fixPath(album.title) if album is not None else ''
    year = _getYear(album.releaseDate) if album is not None else ''

    # extension
    extension = _getExtension(stream)

    retpath = SETTINGS.trackFileFormat
    if retpath is None or len(retpath) <= 0:
        retpath = SETTINGS.getDefaultPathFormat(Type.Track)
    hasStreamIdentifier = _hasStreamIdentifierToken(retpath)
    retpath = retpath.replace(R"{TrackNumber}", number)
    retpath = retpath.replace(R"{ArtistName}", trackArtistName)
    retpath = retpath.replace(R"{ArtistsName}", artists)
    retpath = retpath.replace(R"{ArtistID}", artistID)
    retpath = retpath.replace(R"{TrackArtistID}", trackArtistID)
    retpath = retpath.replace(R"{TrackArtistName}", trackArtistName)
    retpath = retpath.replace(R"{TrackTitle}", title)
    retpath = retpath.replace(R"{ExplicitFlag}", explicit)
    retpath = retpath.replace(R"{AlbumYear}", year)
    retpath = retpath.replace(R"{AlbumTitle}", albumName)
    retpath = retpath.replace(R"{AudioQuality}", _tokenValue(track.audioQuality))
    retpath = retpath.replace(R"{StreamQuality}", _fixPath(_getStreamQuality(stream)))
    retpath = retpath.replace(R"{Codec}", _fixPath(stream.codec or ''))
    retpath = retpath.replace(R"{DurationSeconds}", _tokenValue(track.duration or 0))
    retpath = retpath.replace(R"{Duration}", _fixPath(_getDurationStr(track.duration or 0)))
    retpath = retpath.replace(R"{TrackID}", _tokenValue(track.id))
    retpath = retpath.strip()
    if _isAtmosStream(stream) and SETTINGS.audioQuality == AudioQuality.Atmos and not hasStreamIdentifier:
        retpath += " [Dolby Atmos]"
    return os.path.join(base, _safeMediaPath(retpath, extension))


def getVideoPath(video, album=None, playlist=None):
    base = os.path.join(downloadRoot(), 'Video')
    if album is not None and album.title is not None:
        base = getAlbumPath(album)
    elif playlist is not None and SETTINGS.usePlaylistFolder:
        base = getPlaylistPath(playlist)

    # get number
    number = str(video.trackNumber).rjust(2, '0')

    # get artist
    artists = _fixPath(TIDAL_API.getArtistsName(video.artists))
    artistID = _fixPath(TIDAL_API.getArtistsID(video.artists))
    primary_artist = getattr(video, 'artist', None)
    videoArtistID = _fixPath(_tokenValue(getattr(primary_artist, 'id', None)))
    videoArtistName = _fixPath(_tokenValue(getattr(primary_artist, 'name', None)))

    # explicit
    explicit = "(Explicit)" if video.explicit else ''

    # title and year and extension
    title = _fixPath(video.title)
    year = _getYear(video.releaseDate)
    extension = ".mp4"

    retpath = SETTINGS.videoFileFormat
    if retpath is None or len(retpath) <= 0:
        retpath = SETTINGS.getDefaultPathFormat(Type.Video)
    retpath = retpath.replace(R"{VideoNumber}", number)
    retpath = retpath.replace(R"{ArtistName}", videoArtistName)
    retpath = retpath.replace(R"{ArtistID}", artistID)
    retpath = retpath.replace(R"{ArtistsName}", artists)
    retpath = retpath.replace(R"{VideoArtistID}", videoArtistID)
    retpath = retpath.replace(R"{VideoArtistName}", videoArtistName)
    retpath = retpath.replace(R"{VideoTitle}", title)
    retpath = retpath.replace(R"{ExplicitFlag}", explicit)
    retpath = retpath.replace(R"{VideoYear}", year)
    retpath = retpath.replace(R"{VideoID}", str(video.id))
    return os.path.join(base, _safeMediaPath(retpath.strip(), extension))


def openPath(path):
    target = os.path.abspath(os.path.expanduser(path or downloadRoot()))
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

    def _getHomePath(self):
        if self.homePathOverride is None:
            return self._getDefaultHomePath()
        else:
            return self.homePathOverride

    def _getDefaultHomePath(self):
        if "XDG_CONFIG_HOME" in os.environ:
            return os.environ['XDG_CONFIG_HOME']
        elif "HOME" in os.environ:
            return os.environ['HOME']
        elif "HOMEDRIVE" in os.environ and "HOMEPATH" in os.environ:
            return os.environ['HOMEDRIVE'] + os.environ['HOMEPATH']
        else:
            return os.path.abspath("./")

    def getLogPath(self):
        return self._getHomePath() + '/.tidal-dl.log'

    def getTokenPath(self):
        return self._getHomePath() + '/.tidal-dl.token.json'

    def getProfilePath(self):
        return self._getHomePath() + '/.tidal-dl.json'

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
