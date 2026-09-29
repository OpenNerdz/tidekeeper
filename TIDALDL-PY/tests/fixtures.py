"""Shared test fixtures: stub HTTP responses, catalog builders, and isolated state."""

import copy
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import requests

from tidal_dl import download
from tidal_dl.model import StreamUrl
from tidal_dl.settings import SETTINGS, TOKEN
from tidal_dl.tidal import TidalAPI


def response(content=b'', headers=None, status=200, url='https://cdn.example/media'):
    """A finished requests.Response with fixed content and a mock close()."""
    result = requests.Response()
    result.status_code = status
    result._content = content
    result._content_consumed = True
    result.headers.update(headers or {})
    result.url = url
    result.close = mock.Mock()
    return result


class FakeResponse:
    """Minimal streamed response for transfer tests."""

    def __init__(self, content=b'', status=200, headers=None, body=None):
        self.content = content
        self.status_code = status
        self.headers = headers or {'Content-Length': str(len(content))}
        self.body = body
        self.closed = False

    def json(self):
        return self.body

    @property
    def text(self):
        if self.body is not None:
            return json.dumps(self.body)
        if isinstance(self.content, bytes):
            return self.content.decode('utf-8', 'replace')
        return '' if self.content is None else str(self.content)

    def iter_content(self, chunk_size):
        yield self.content

    def close(self):
        self.closed = True

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code), response=self)


def playback_params(audioquality, prefetch=False):
    """Query parameters sent for a playback-info request."""
    params = {
        "audioquality": audioquality,
        "playbackmode": "STREAM",
        "assetpresentation": "FULL",
    }
    if prefetch:
        params["prefetch"] = "false"
    return params


class TransferFixture:
    """Temporary folder and restored settings, with media URL checks disabled for local fixtures."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = copy.deepcopy(SETTINGS.__dict__)
        self.addCleanup(self.restore_settings)
        url_policy = mock.patch.object(download, 'validate_media_url', return_value=True)
        url_policy.start()
        self.addCleanup(url_policy.stop)

    def restore_settings(self):
        SETTINGS.__dict__.clear()
        SETTINGS.__dict__.update(self.settings)


class ProfileFixture:
    """Temporary folder; the settings profile and saved login are restored after each test."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for singleton in (SETTINGS, TOKEN):
            original = copy.deepcopy(singleton.__dict__)
            self.addCleanup(self.restore, singleton, original)

    @staticmethod
    def restore(singleton, values):
        singleton.__dict__.clear()
        singleton.__dict__.update(values)


class ApiFixture:
    """Temporary folder, restored settings, and a fresh API client."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        saved = copy.deepcopy(SETTINGS.__dict__)

        def restore():
            SETTINGS.__dict__.clear()
            SETTINGS.__dict__.update(saved)

        self.addCleanup(restore)
        self.api = TidalAPI()
        self.addCleanup(self.api.session.close)


class DownloadFolderApiFixture:
    """Temporary download folder, restored settings, and a fresh API client."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        saved = copy.deepcopy(SETTINGS.__dict__)
        def restore():
            SETTINGS.__dict__.clear()
            SETTINGS.__dict__.update(saved)
        self.addCleanup(restore)
        SETTINGS.downloadPath = str(self.root)
        self.api = TidalAPI()
        self.addCleanup(self.api.session.close)


class CatalogFixtures:
    """Builders for minimal catalog objects."""

    def _artist(self, name="Artist", id=123):
        return SimpleNamespace(name=name, id=id)

    def _album(self):
        artist = self._artist()
        return SimpleNamespace(
            id=123,
            artists=[artist],
            artist=artist,
            title="Album",
            releaseDate="2026-01-02",
            audioQuality="HIGH",
            audioModes=[],
            explicit=False,
            duration=180,
            numberOfTracks=1,
            numberOfVideos=0,
            numberOfVolumes=1,
            type="ALBUM",
            cover=None,
        )

    def _track(self):
        artist = self._artist()
        album = SimpleNamespace(id=123, title="Album")
        return SimpleNamespace(
            id=456,
            artists=[artist],
            artist=artist,
            album=album,
            title="Track",
            version=None,
            explicit=False,
            trackNumber=1,
            trackNumberOnPlaylist=1,
            volumeNumber=1,
            audioQuality="HIGH",
            duration=180,
        )

    def _video(self):
        artist = self._artist()
        album = self._album()
        return SimpleNamespace(
            id=789,
            artists=[artist],
            artist=artist,
            album=album,
            title="Video",
            explicit=False,
            trackNumber=1,
            releaseDate="2026-01-02",
        )

    def _playlist(self):
        return SimpleNamespace(uuid="playlist-uuid", title="Playlist")

    def _stream(self):
        stream = StreamUrl()
        stream.url = "https://example.invalid/audio.m4a"
        stream.urls = [stream.url]
        stream.codec = "aac"
        stream.container = "mp4"
        stream.manifestMimeType = "application/dash+xml"
        stream.soundQuality = "HIGH"
        return stream

    def _dash_manifest(self, codec="flac"):
        return (
            "<?xml version='1.0' encoding='UTF-8'?>"
            "<MPD xmlns=\"urn:mpeg:dash:schema:mpd:2011\">"
            "<Period><AdaptationSet contentType=\"audio\">"
            f"<Representation codecs=\"{codec}\">"
            "<SegmentTemplate initialization=\"https://example.invalid/init.mp4\" "
            "media=\"https://example.invalid/$Number$.mp4\" startNumber=\"1\">"
            "<SegmentTimeline><S d=\"1024\" r=\"1\" /></SegmentTimeline>"
            "</SegmentTemplate>"
            "</Representation>"
            "</AdaptationSet></Period>"
            "</MPD>"
        )
