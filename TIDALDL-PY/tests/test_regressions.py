import base64
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import tidal_dl
from tidal_dl import apiKey, download, events, paths
from tidal_dl.enums import AudioQuality, Type
from tidal_dl.gui_app.backend import TidekeeperBackend, SearchItem, with_video_only
from tidal_dl.model import Artist, StreamUrl
from tidal_dl.settings import Settings
from tidal_dl.tidal import API_BASE_PRIMARY, TidalAPI, TidalApiError


def _playback_params(audioquality, prefetch=False):
    params = {
        "audioquality": audioquality,
        "playbackmode": "STREAM",
        "assetpresentation": "FULL",
    }
    if prefetch:
        params["prefetch"] = "false"
    return params


class CliAuthPathRegressionTests(unittest.TestCase):
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

    def test_device_auth_pending_without_status_keeps_waiting(self):
        api = TidalAPI()
        api.key.deviceCode = "device-code"

        with mock.patch.object(api, "__post__", return_value={"error": "authorization_pending"}):
            self.assertFalse(api.checkAuthStatus())

    def test_link_command_aborts_when_login_fails(self):
        old_argv = sys.argv
        sys.argv = ["tidekeeper", "--link", "123456"]
        try:
            with mock.patch.object(tidal_dl.aigpy.path, "mkdirs", return_value=True), \
                 mock.patch.object(tidal_dl, "loginByConfig", return_value=False), \
                 mock.patch.object(tidal_dl, "loginByWeb", return_value=False), \
                 mock.patch.object(tidal_dl, "start") as start:
                tidal_dl.mainCommand()
        finally:
            sys.argv = old_argv

        start.assert_not_called()

    def test_doctor_command_runs_without_login_or_download(self):
        old_argv = sys.argv
        sys.argv = ["tidekeeper", "--doctor"]
        try:
            with mock.patch.object(tidal_dl, "runDoctor", return_value=True) as doctor, \
                 mock.patch.object(tidal_dl, "loginByConfig") as login, \
                 mock.patch.object(tidal_dl, "start") as start:
                tidal_dl.mainCommand()
        finally:
            sys.argv = old_argv

        doctor.assert_called_once_with()
        login.assert_not_called()
        start.assert_not_called()

    def test_empty_path_formats_use_default_formats(self):
        old_values = {
            "downloadPath": paths.SETTINGS.downloadPath,
            "albumFolderFormat": paths.SETTINGS.albumFolderFormat,
            "playlistFolderFormat": paths.SETTINGS.playlistFolderFormat,
            "trackFileFormat": paths.SETTINGS.trackFileFormat,
            "videoFileFormat": paths.SETTINGS.videoFileFormat,
            "usePlaylistFolder": paths.SETTINGS.usePlaylistFolder,
        }
        try:
            paths.SETTINGS.downloadPath = "/tmp/tidekeeper"
            paths.SETTINGS.albumFolderFormat = ""
            paths.SETTINGS.playlistFolderFormat = ""
            paths.SETTINGS.trackFileFormat = ""
            paths.SETTINGS.videoFileFormat = ""
            paths.SETTINGS.usePlaylistFolder = True

            self.assertIn("Album [123] [2026]", paths.getAlbumPath(self._album()))
            self.assertIn("Playlist [playlist-uuid]", paths.getPlaylistPath(self._playlist()))
            self.assertTrue(paths.getTrackPath(self._track(), self._stream(), self._album()).endswith("01 - Artist - Track.m4a"))
            self.assertTrue(paths.getVideoPath(self._video()).endswith("01 - Artist - Video.mp4"))
        finally:
            for key, value in old_values.items():
                setattr(paths.SETTINGS, key, value)

    def test_get_album_converts_each_artist_to_model(self):
        api = TidalAPI()
        payload = {
            "id": 123,
            "title": "Album",
            "artist": {"id": 123, "name": "Artist One"},
            "artists": [
                {"id": 123, "name": "Artist One"},
                {"id": 456, "name": "Artist Two"},
            ],
        }

        with mock.patch.object(api, "__get__", return_value=payload):
            album = api.getAlbum(123)

        self.assertEqual([artist.id for artist in album.artists], [123, 456])
        self.assertEqual([artist.name for artist in album.artists], ["Artist One", "Artist Two"])

    def test_get_track_converts_each_artist_to_model(self):
        api = TidalAPI()
        payload = {
            "id": 456,
            "title": "Track",
            "artist": {"id": 123, "name": "Artist One"},
            "artists": [
                {"id": 123, "name": "Artist One"},
                {"id": 456, "name": "Artist Two"},
            ],
            "album": {"id": 1, "title": "Album"},
        }

        with mock.patch.object(api, "__get__", return_value=payload):
            track = api.getTrack(456)

        self.assertEqual([artist.id for artist in track.artists], [123, 456])
        self.assertEqual([artist.name for artist in track.artists], ["Artist One", "Artist Two"])

    def test_artists_helpers_tolerate_none_and_missing_names(self):
        api = TidalAPI()
        self.assertEqual(api.getArtistsName(None), "")
        self.assertEqual(api.getArtistsID(None), "")
        self.assertEqual(api.getArtistsName([self._artist(None, 1), None]), "")
        self.assertEqual(api.getArtistsID([self._artist("A", None), self._artist("B", 2)]), "2")

    def test_search_result_items_default_to_empty_list(self):
        api = TidalAPI()
        result = SimpleNamespace(
            tracks=SimpleNamespace(items=None),
            videos=SimpleNamespace(items=None),
            albums=SimpleNamespace(items=None),
            artists=SimpleNamespace(items=None),
            playlists=SimpleNamespace(items=None),
        )
        self.assertEqual(api.getSearchResultItems(result, Type.Track), [])
        self.assertEqual(api.getSearchResultItems(None, Type.Album), [])

    def test_get_by_string_surfaces_auth_errors(self):
        api = TidalAPI()
        with mock.patch.object(api, "getTypeData", side_effect=TidalApiError("auth failed", 401)):
            with self.assertRaises(TidalApiError) as raised:
                api.getByString("123456")
        self.assertEqual(raised.exception.statusCode, 401)

    def test_get_by_string_surfaces_forbidden_errors(self):
        api = TidalAPI()
        with mock.patch.object(api, "getTypeData", side_effect=TidalApiError("forbidden", 403)):
            with self.assertRaises(TidalApiError) as raised:
                api.getByString("123456")
        self.assertEqual(raised.exception.statusCode, 403)

    def test_get_by_string_surfaces_network_errors(self):
        import requests

        api = TidalAPI()
        with mock.patch.object(api, "getTypeData", side_effect=requests.ConnectionError("offline")):
            with self.assertRaises(requests.ConnectionError):
                api.getByString("123456")

    def test_album_path_tolerates_missing_optional_tokens(self):
        album = self._album()
        album.audioQuality = None
        album.type = None
        album.numberOfVolumes = None
        album.releaseDate = None
        album.duration = None
        album.numberOfTracks = None
        album.numberOfVideos = None

        with mock.patch.object(
            paths.SETTINGS,
            "albumFolderFormat",
            "{AlbumTitle}/{AudioQuality}/{RecordType}/{NumberOfVolumes}",
        ), mock.patch.object(paths.SETTINGS, "downloadPath", "/tmp/tidekeeper"):
            path = paths.getAlbumPath(album)

        self.assertEqual(path, "/tmp/tidekeeper/Album///0")

    def test_album_items_include_tracks_when_stream_ready_missing(self):
        api = TidalAPI()
        api.__getItems__ = lambda path: [
            {"type": "track", "item": {"id": 1, "title": "Legacy Ready"}},
            {"type": "track", "item": {"id": 2, "streamReady": False, "title": "Unavailable"}},
        ]

        tracks, videos = api.getItems("album-id", Type.Album)

        self.assertEqual([track.id for track in tracks], [1])
        self.assertEqual(videos, [])

    def test_album_path_replaces_album_artist_ids_for_singular_artist(self):
        album = self._album()
        album.artist = self._artist("Artist One", 123)

        with mock.patch.object(paths.SETTINGS, "albumFolderFormat", "{AlbumArtistID}/{AlbumTitle}"):
            self.assertTrue(paths.getAlbumPath(album).endswith("123/Album"))

    def test_album_path_replaces_artist_ids_for_multiple_artists(self):
        album = self._album()
        album.artists = [self._artist("Artist One", 123), self._artist("Artist Two", 456)]

        with mock.patch.object(paths.SETTINGS, "albumFolderFormat", "{ArtistID}/{AlbumTitle}"):
            self.assertTrue(paths.getAlbumPath(album).endswith("123, 456/Album"))

    def test_album_items_skip_unstreamable_tracks_instead_of_treating_them_as_videos(self):
        api = TidalAPI()
        api.__getItems__ = lambda path: [
            {"type": "track", "item": {"id": 1, "streamReady": True, "title": "Ready"}},
            {"type": "track", "item": {"id": 2, "streamReady": False, "title": "Unavailable"}},
            {"type": "video", "item": {"id": 3, "title": "Video"}},
        ]

        tracks, videos = api.getItems("album-id", Type.Album)

        self.assertEqual([track.id for track in tracks], [1])
        self.assertEqual([video.id for video in videos], [3])

    def test_artist_videos_fetches_artist_video_endpoint(self):
        api = TidalAPI()
        calls = []

        def fake_items(path, params=None):
            calls.append((path, params))
            return [
                {"id": 10, "title": "Video One"},
                {"type": "video", "item": {"id": 20, "title": "Video Two"}},
            ]

        api.__getItems__ = fake_items

        videos = api.getArtistVideos(99)

        self.assertEqual(calls, [("artists/99/videos", None)])
        self.assertEqual([video.id for video in videos], [10, 20])
        self.assertEqual([video.title for video in videos], ["Video One", "Video Two"])

    def test_mix_lookup_returns_mix_object(self):
        api = TidalAPI()
        track = self._track()
        video = self._video()

        with mock.patch.object(api, "getItems", return_value=([track], [video])):
            mix = api.getMix("mix-id")

        self.assertEqual(mix.id, "mix-id")
        self.assertEqual(mix.tracks, [track])
        self.assertEqual(mix.videos, [video])

    def test_artist_video_only_downloads_artist_videos_without_album_audio(self):
        artist = SimpleNamespace(id=99, name="Artist", type="MAIN")
        video = self._video()
        video.id = 10

        with mock.patch.object(events.TIDAL_API, "getArtistVideos", return_value=[video]) as artist_videos, \
             mock.patch.object(events.TIDAL_API, "getArtistAlbums") as artist_albums, \
             mock.patch.object(events, "start_album") as start_album, \
             mock.patch.object(events, "downloadVideos") as download_videos:
            events.start_artist(artist, videoOnly=True)

        artist_videos.assert_called_once_with(99)
        artist_albums.assert_not_called()
        start_album.assert_not_called()
        download_videos.assert_called_once_with([video], None)

    def test_manual_access_token_login_persists_userid(self):
        old_values = {
            "userid": events.TOKEN.userid,
            "countryCode": events.TOKEN.countryCode,
            "accessToken": events.TOKEN.accessToken,
            "refreshToken": events.TOKEN.refreshToken,
            "expiresAfter": events.TOKEN.expiresAfter,
        }
        try:
            events.TOKEN.userid = None
            events.TOKEN.countryCode = None
            events.TOKEN.accessToken = None
            events.TOKEN.refreshToken = "old-refresh"
            events.TOKEN.expiresAfter = 0

            def fake_login(access_token, userid=None):
                events.TIDAL_API.key.userId = "user-123"
                events.TIDAL_API.key.countryCode = "GB"
                events.TIDAL_API.key.accessToken = access_token

            with mock.patch.object(events.Printf, "enter", side_effect=["access-token", "0"]), \
                 mock.patch.object(events.TIDAL_API, "loginByAccessToken", fake_login), \
                 mock.patch.object(events.TOKEN, "save"):
                events.loginByAccessToken()

            self.assertEqual(events.TOKEN.userid, "user-123")
            self.assertEqual(events.TOKEN.countryCode, "GB")
        finally:
            for key, value in old_values.items():
                setattr(events.TOKEN, key, value)

    def test_refresh_access_token_preserves_rotated_refresh_token(self):
        api = TidalAPI()
        result = {
            "user": {"userId": "user-123", "countryCode": "GB"},
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 3600,
        }

        with mock.patch.object(api, "__post__", return_value=result):
            self.assertTrue(api.refreshAccessToken("old-refresh"))

        self.assertEqual(api.key.refreshToken, "new-refresh")

    def test_login_by_config_persists_rotated_refresh_token(self):
        old_values = {
            "userid": events.TOKEN.userid,
            "countryCode": events.TOKEN.countryCode,
            "accessToken": events.TOKEN.accessToken,
            "refreshToken": events.TOKEN.refreshToken,
            "expiresAfter": events.TOKEN.expiresAfter,
        }
        try:
            events.TOKEN.userid = "user-123"
            events.TOKEN.countryCode = "GB"
            events.TOKEN.accessToken = "expired-access"
            events.TOKEN.refreshToken = "old-refresh"
            events.TOKEN.expiresAfter = 0

            def fake_refresh(refresh_token):
                events.TIDAL_API.key.userId = "user-123"
                events.TIDAL_API.key.countryCode = "GB"
                events.TIDAL_API.key.accessToken = "new-access"
                events.TIDAL_API.key.refreshToken = "new-refresh"
                events.TIDAL_API.key.expiresIn = 3600
                return True

            with mock.patch.object(events.TIDAL_API, "verifyAccessToken", return_value=False), \
                 mock.patch.object(events.TIDAL_API, "refreshAccessToken", fake_refresh), \
                 mock.patch.object(events.TOKEN, "save"):
                self.assertTrue(events.loginByConfig())

            self.assertEqual(events.TOKEN.refreshToken, "new-refresh")
        finally:
            for key, value in old_values.items():
                setattr(events.TOKEN, key, value)

    def test_api_get_refreshes_saved_token_after_unauthorized_response(self):
        api = TidalAPI()
        old_values = {
            "userid": events.TOKEN.userid,
            "countryCode": events.TOKEN.countryCode,
            "accessToken": events.TOKEN.accessToken,
            "refreshToken": events.TOKEN.refreshToken,
            "expiresAfter": events.TOKEN.expiresAfter,
        }

        def fake_response(status, body):
            text = json.dumps(body)
            return SimpleNamespace(
                status_code=status,
                url="https://api.tidalhifi.com/v1/albums/123",
                text=text,
                json=lambda: body,
                close=mock.Mock(),
            )

        try:
            events.TOKEN.userid = "user-123"
            events.TOKEN.countryCode = "GB"
            events.TOKEN.accessToken = "expired-access"
            events.TOKEN.refreshToken = "refresh-token"
            events.TOKEN.expiresAfter = 0
            api.key.accessToken = "expired-access"
            api.key.countryCode = "GB"

            def fake_refresh(refresh_token):
                self.assertEqual(refresh_token, "refresh-token")
                api.key.userId = "user-123"
                api.key.countryCode = "GB"
                api.key.accessToken = "fresh-access"
                api.key.refreshToken = "fresh-refresh"
                api.key.expiresIn = 3600
                return True

            with mock.patch.object(api, "refreshAccessToken", side_effect=fake_refresh), \
                 mock.patch.object(events.TOKEN, "save") as save, \
                 mock.patch.object(api.session, "get", side_effect=[
                     fake_response(401, {"status": 401}),
                     fake_response(200, {"id": 123, "title": "Album"}),
                 ]) as get:
                data = api.__get__("albums/123")

            self.assertEqual(data["title"], "Album")
            self.assertEqual(events.TOKEN.accessToken, "fresh-access")
            self.assertEqual(events.TOKEN.refreshToken, "fresh-refresh")
            save.assert_called_once_with()
            self.assertEqual(get.call_args_list[0].kwargs["headers"]["authorization"], "Bearer expired-access")
            self.assertEqual(get.call_args_list[1].kwargs["headers"]["authorization"], "Bearer fresh-access")
        finally:
            for key, value in old_values.items():
                setattr(events.TOKEN, key, value)

    def test_playback_asset_not_ready_retries_before_failing(self):
        api = TidalAPI()
        manifest = base64.b64encode(json.dumps({
            "codecs": "flac",
            "urls": ["https://example.invalid/track.flac"],
            "mimeType": "audio/flac",
        }).encode("utf-8")).decode("utf-8")

        def fake_response(status_code, payload):
            return SimpleNamespace(
                status_code=status_code,
                text=json.dumps(payload),
                headers={},
                close=mock.Mock(),
                json=mock.Mock(return_value=payload),
            )

        old_delay = events.SETTINGS.downloadDelay
        try:
            events.SETTINGS.downloadDelay = False
            with mock.patch.object(api, "__refreshSavedAccessToken__", return_value=False), \
                 mock.patch("tidal_dl.tidal.time.sleep") as sleep, \
                 mock.patch.object(api.session, "get", side_effect=[
                     fake_response(401, {"status": 401, "subStatus": 4005, "userMessage": "Asset is not ready for playback"}),
                     fake_response(200, {
                         "trackid": 123,
                         "audioQuality": "LOSSLESS",
                         "manifestMimeType": "application/vnd.tidal.bt",
                         "manifest": manifest,
                     }),
                 ]):
                data = api.__getOnce__(
                    "tracks/123/playbackinfopostpaywall/v4",
                    _playback_params("LOSSLESS"),
                    API_BASE_PRIMARY,
                )

            self.assertEqual(data["trackid"], 123)
            sleep.assert_called_once_with(5)
        finally:
            events.SETTINGS.downloadDelay = old_delay

    def test_playback_api_requests_use_rate_limiter(self):
        api = TidalAPI()
        old_delay = events.SETTINGS.downloadDelay
        limiter = SimpleNamespace(wait=mock.Mock())
        response = SimpleNamespace(
            status_code=200,
            text=json.dumps({"ok": True}),
            headers={},
            url="https://api.tidal.com/v1/tracks/123/playbackinfopostpaywall/v4",
        )
        try:
            events.SETTINGS.downloadDelay = True
            api.playbackRateLimiter = limiter
            with mock.patch.object(api.session, "get", return_value=response):
                self.assertEqual(api.__get__("tracks/123/playbackinfopostpaywall/v4"), {"ok": True})

            limiter.wait.assert_called_once_with()
        finally:
            events.SETTINGS.downloadDelay = old_delay

    def test_openapi_rate_limit_penalizes_shared_limiter(self):
        api = TidalAPI()
        limiter = SimpleNamespace(wait=mock.Mock(), penalize=mock.Mock(return_value=17.0), reward=mock.Mock())
        rate_limited = SimpleNamespace(
            status_code=429,
            text="rate limited",
            headers={"Retry-After": "17"},
            close=mock.Mock(),
            json=mock.Mock(return_value={}),
        )
        success = SimpleNamespace(
            status_code=200,
            text='{"data":{"attributes":{"formats":["FLAC"]}}}',
            headers={},
            close=mock.Mock(),
            json=mock.Mock(return_value={"data": {"attributes": {"formats": ["FLAC"]}}}),
        )
        old_values = (
            events.SETTINGS.downloadDelay,
            events.SETTINGS.adaptiveRateLimit,
            events.SETTINGS.requestIntervalSeconds,
        )
        try:
            events.SETTINGS.downloadDelay = True
            events.SETTINGS.adaptiveRateLimit = True
            events.SETTINGS.requestIntervalSeconds = 3.0
            api.playbackRateLimiter = limiter
            with mock.patch.object(api.session, "get", side_effect=[rate_limited, success]), \
                 mock.patch("tidal_dl.tidal.time.sleep") as sleep:
                attrs = api.__getOpenApiTrackManifest__(456, ["FLAC"])

            self.assertEqual(attrs["formats"], ["FLAC"])
            limiter.penalize.assert_called_once_with(17.0)
            self.assertEqual(limiter.wait.call_count, 2)
            limiter.reward.assert_called_once_with()
            sleep.assert_called_once_with(17.0)
        finally:
            (
                events.SETTINGS.downloadDelay,
                events.SETTINGS.adaptiveRateLimit,
                events.SETTINGS.requestIntervalSeconds,
            ) = old_values

    def test_openapi_manifest_requests_use_rate_limiter(self):
        api = TidalAPI()
        old_delay = events.SETTINGS.downloadDelay
        limiter = SimpleNamespace(wait=mock.Mock())
        payload = {"data": {"attributes": {"formats": ["FLAC"], "uri": "data:x,eyJ0ZXN0In0="}}}
        response = SimpleNamespace(
            status_code=200,
            text=json.dumps(payload),
            headers={},
            close=mock.Mock(),
            json=mock.Mock(return_value=payload),
        )
        try:
            events.SETTINGS.downloadDelay = True
            api.playbackRateLimiter = limiter
            with mock.patch.object(api.session, "get", return_value=response):
                attrs = api.__getOpenApiTrackManifest__(456, ["FLAC"])

            self.assertEqual(attrs["formats"], ["FLAC"])
            limiter.wait.assert_called_once_with()
        finally:
            events.SETTINGS.downloadDelay = old_delay

    def test_playback_rate_limit_skips_openapi_manifest(self):
        api = TidalAPI()

        with mock.patch.object(
            api,
            "__getPlaybackData__",
            side_effect=TidalApiError("Get operation failed: HTTP 429", statusCode=429),
        ) as playback_get, mock.patch.object(
            api,
            "__getOpenApiTrackManifest__",
        ) as openapi_get:
            with self.assertRaises(TidalApiError) as ctx:
                api.getStreamUrlByPriority(456, [AudioQuality.HiFi])

        self.assertIn("429", str(ctx.exception))
        playback_get.assert_called_once()
        openapi_get.assert_not_called()

    def test_playback_403_does_not_retry(self):
        api = TidalAPI()
        old_delay = events.SETTINGS.downloadDelay
        response = SimpleNamespace(
            status_code=403,
            text='{"errors":[{"code":"CLIENT_NOT_ENTITLED"}]}',
            headers={},
            close=mock.Mock(),
            json=mock.Mock(return_value={"errors": [{"code": "CLIENT_NOT_ENTITLED"}]}),
        )
        try:
            events.SETTINGS.downloadDelay = False
            with mock.patch.object(api.session, "get", return_value=response) as get_mock:
                with self.assertRaises(TidalApiError) as ctx:
                    api.__getOnce__(
                        "tracks/456/playbackinfopostpaywall/v4",
                        _playback_params("LOSSLESS"),
                        API_BASE_PRIMARY,
                    )

            self.assertEqual(ctx.exception.statusCode, 403)
            self.assertEqual(get_mock.call_count, 1)
        finally:
            events.SETTINGS.downloadDelay = old_delay

    def test_blocked_playback_param_skips_repeat_probe(self):
        api = TidalAPI()
        api._playbackBlockedParams.add("LOSSLESS")
        uri = "data:application/dash+xml;base64," + base64.b64encode(
            self._dash_manifest("flac").encode("utf-8")
        ).decode("utf-8")

        with mock.patch.object(api, "__getPlaybackData__") as playback_get, mock.patch.object(
            api,
            "__getOpenApiTrackManifest__",
            return_value={"formats": ["FLAC"], "uri": uri},
        ):
            stream = api.getStreamUrlByPriority(456, [AudioQuality.HiFi])

        playback_get.assert_not_called()
        self.assertEqual(stream.soundQuality, "LOSSLESS")

    def test_manifest_rate_limit_fails_after_max_attempts(self):
        api = TidalAPI()
        old_delay = events.SETTINGS.downloadDelay
        try:
            events.SETTINGS.downloadDelay = False
            response = SimpleNamespace(
                status_code=429,
                text='{"errors":[{"status":"429"}]}',
                headers={},
                close=mock.Mock(),
                json=mock.Mock(return_value={"errors": [{"status": "429"}]}),
            )
            with mock.patch.object(api.session, "get", return_value=response) as get_mock, \
                 mock.patch("tidal_dl.tidal.time.sleep"), \
                 mock.patch("builtins.print"):
                with self.assertRaises(TidalApiError) as ctx:
                    api.__getOpenApiTrackManifest__(456, ["FLAC"])

            self.assertEqual(ctx.exception.statusCode, 429)
            self.assertEqual(get_mock.call_count, 3)
        finally:
            events.SETTINGS.downloadDelay = old_delay

    def test_gui_backend_syncs_saved_country_code_before_search(self):
        old_values = {
            "userid": events.TOKEN.userid,
            "countryCode": events.TOKEN.countryCode,
            "accessToken": events.TOKEN.accessToken,
            "refreshToken": events.TOKEN.refreshToken,
            "expiresAfter": events.TOKEN.expiresAfter,
            "api_user": events.TIDAL_API.key.userId,
            "api_country": events.TIDAL_API.key.countryCode,
            "api_access": events.TIDAL_API.key.accessToken,
            "api_refresh": events.TIDAL_API.key.refreshToken,
        }
        try:
            events.TOKEN.userid = "user-123"
            events.TOKEN.countryCode = "GB"
            events.TOKEN.accessToken = "saved-access"
            events.TOKEN.refreshToken = "saved-refresh"
            events.TOKEN.expiresAfter = time.time() + 3600
            events.TIDAL_API.key.userId = None
            events.TIDAL_API.key.countryCode = None
            events.TIDAL_API.key.accessToken = None
            events.TIDAL_API.key.refreshToken = None

            backend = TidekeeperBackend()
            backend._ensure_catalog_session()

            self.assertEqual(events.TIDAL_API.key.userId, "user-123")
            self.assertEqual(events.TIDAL_API.key.countryCode, "GB")
            self.assertEqual(events.TIDAL_API.key.accessToken, "saved-access")
        finally:
            for key, value in old_values.items():
                if key.startswith("api_"):
                    attr = {
                        "api_user": "userId",
                        "api_country": "countryCode",
                        "api_access": "accessToken",
                        "api_refresh": "refreshToken",
                    }[key]
                    setattr(events.TIDAL_API.key, attr, value)
                else:
                    setattr(events.TOKEN, key, value)

    def test_gui_backend_recovers_missing_saved_country_code(self):
        old_values = {
            "userid": events.TOKEN.userid,
            "countryCode": events.TOKEN.countryCode,
            "accessToken": events.TOKEN.accessToken,
            "refreshToken": events.TOKEN.refreshToken,
            "expiresAfter": events.TOKEN.expiresAfter,
        }
        try:
            events.TOKEN.userid = "user-123"
            events.TOKEN.countryCode = None
            events.TOKEN.accessToken = "saved-access"
            events.TOKEN.refreshToken = "saved-refresh"
            events.TOKEN.expiresAfter = time.time() + 3600

            def fake_login(access_token, userid=None):
                events.TIDAL_API.key.userId = userid
                events.TIDAL_API.key.countryCode = "GB"
                events.TIDAL_API.key.accessToken = access_token
                events.TIDAL_API.key.refreshToken = events.TOKEN.refreshToken

            backend = TidekeeperBackend()
            with mock.patch.object(events.TIDAL_API, "loginByAccessToken", fake_login), \
                 mock.patch.object(events.TOKEN, "save"):
                backend._ensure_catalog_session()

            self.assertEqual(events.TOKEN.countryCode, "GB")
            self.assertEqual(events.TIDAL_API.key.countryCode, "GB")
        finally:
            for key, value in old_values.items():
                setattr(events.TOKEN, key, value)

    def test_gui_backend_artist_tracks_expands_albums_without_duplicates(self):
        artist = SimpleNamespace(id=99, name="Artist")
        album_one = SimpleNamespace(id=10, title="First")
        album_two = SimpleNamespace(id=20, title="Second")
        track_one = self._track()
        track_one.id = 1
        track_one.title = "One"
        track_two = self._track()
        track_two.id = 2
        track_two.title = "Two"

        def fake_items(album_id, etype):
            self.assertEqual(etype, Type.Album)
            if album_id == 10:
                return [track_one, track_two], []
            return [track_one], []

        backend = TidekeeperBackend()
        search_item = SimpleNamespace(source=artist, identifier="99")
        with mock.patch.object(backend, "_ensure_catalog_session"), \
             mock.patch.object(events.TIDAL_API, "getArtistAlbums", return_value=[album_one, album_one, album_two]), \
             mock.patch.object(events.TIDAL_API, "getItems", side_effect=fake_items):
            tracks = backend.artist_tracks(search_item)

        self.assertEqual([item.identifier for item in tracks], ["1", "2"])
        self.assertEqual([item.kind for item in tracks], [Type.Track, Type.Track])

    def test_gui_backend_artist_videos_fetches_videos_without_duplicates(self):
        artist = SimpleNamespace(id=99, name="Artist")
        video_one = self._video()
        video_one.id = 1
        video_one.title = "One"
        video_two = self._video()
        video_two.id = 2
        video_two.title = "Two"

        backend = TidekeeperBackend()
        search_item = SimpleNamespace(source=artist, identifier="99")
        with mock.patch.object(backend, "_ensure_catalog_session"), \
             mock.patch.object(events.TIDAL_API, "getArtistVideos", return_value=[video_one, video_one, video_two]):
            videos = backend.artist_videos(search_item)

        self.assertEqual([item.identifier for item in videos], ["1", "2"])
        self.assertEqual([item.kind for item in videos], [Type.Video, Type.Video])

    def test_download_tracks_reuses_album_fetches_and_covers(self):
        old_values = {
            "saveCovers": download.SETTINGS.saveCovers,
            "usePlaylistFolder": download.SETTINGS.usePlaylistFolder,
            "multiThread": download.SETTINGS.multiThread,
        }
        album = self._album()
        track_one = self._track()
        track_two = self._track()
        track_one.id = 1
        track_two.id = 2
        track_one.album = SimpleNamespace(id=album.id)
        track_two.album = SimpleNamespace(id=album.id)
        try:
            download.SETTINGS.saveCovers = True
            download.SETTINGS.usePlaylistFolder = False
            download.SETTINGS.multiThread = False

            with mock.patch.object(download.TIDAL_API, "getAlbum", return_value=album) as get_album, \
                 mock.patch.object(download, "downloadCover", return_value=(True, "")) as cover, \
                 mock.patch.object(download, "downloadTrack", return_value=(True, "")) as track_download:
                self.assertTrue(download.downloadTracks([track_one, track_two], None, self._playlist()))

            get_album.assert_called_once_with(album.id)
            cover.assert_called_once_with(album)
            self.assertEqual(track_download.call_count, 2)
        finally:
            for key, value in old_values.items():
                setattr(download.SETTINGS, key, value)

    def test_gui_backend_download_honors_video_only_flag(self):
        backend = TidekeeperBackend()
        item = SearchItem(Type.Artist, "Artist", "", "", "99", "", SimpleNamespace(id=99))
        item = with_video_only(item, True)

        with mock.patch.object(backend, "_ensure_catalog_session"), \
             mock.patch("tidal_dl.gui_app.backend.start_type") as start_type:
            backend.download(item)

        start_type.assert_called_once_with(Type.Artist, item.source, True)

    def test_gui_backend_all_search_combines_catalog_types(self):
        artist = SimpleNamespace(id=99, name="Artist")
        album = self._album()
        track = self._track()

        def fake_items(result, etype):
            return {
                Type.Artist: [artist],
                Type.Album: [album],
                Type.Track: [track],
                Type.Playlist: [],
                Type.Video: [],
            }[etype]

        backend = TidekeeperBackend()
        with mock.patch.object(backend, "_ensure_catalog_session"), \
             mock.patch.object(events.TIDAL_API, "search", return_value=object()), \
             mock.patch.object(events.TIDAL_API, "getSearchResultItems", side_effect=fake_items):
            items = backend.search("artist", Type.Null)

        self.assertEqual([item.kind for item in items], [Type.Artist, Type.Album, Type.Track])
        self.assertEqual([item.title for item in items], ["Artist", "Album", "Track"])

    def test_invalid_api_key_index_returns_error_key_dict(self):
        self.assertFalse(apiKey.isItemValid(999))
        self.assertEqual(apiKey.getItem(999)["platform"], "None")

    def test_album_flag_handles_missing_audio_modes(self):
        album = SimpleNamespace(audioQuality="LOW", audioModes=None, explicit=False)
        self.assertEqual(TidalAPI().getFlag(album, Type.Album), "")

    def test_get_cover_data_uses_timeout(self):
        api = TidalAPI()
        response = SimpleNamespace(content=b"cover")
        with mock.patch.object(api.session, "get", return_value=response) as get:
            self.assertEqual(api.getCoverData("abc-def"), b"cover")

        self.assertEqual(get.call_args.kwargs["timeout"], (5, 60))

    def test_video_path_respects_playlist_folder_setting(self):
        old_values = {
            "downloadPath": paths.SETTINGS.downloadPath,
            "usePlaylistFolder": paths.SETTINGS.usePlaylistFolder,
            "albumFolderFormat": paths.SETTINGS.albumFolderFormat,
            "playlistFolderFormat": paths.SETTINGS.playlistFolderFormat,
            "videoFileFormat": paths.SETTINGS.videoFileFormat,
        }
        try:
            paths.SETTINGS.downloadPath = "/tmp/tidekeeper"
            paths.SETTINGS.usePlaylistFolder = False
            paths.SETTINGS.albumFolderFormat = "{AlbumTitle}"
            paths.SETTINGS.playlistFolderFormat = "Playlist/{PlaylistName}"
            paths.SETTINGS.videoFileFormat = "{VideoNumber} - {VideoTitle}"

            video_path = paths.getVideoPath(self._video(), None, self._playlist())

            self.assertTrue(video_path.startswith("/tmp/tidekeeper/Video/"))
            self.assertNotIn("Playlist/Playlist", video_path)
        finally:
            for key, value in old_values.items():
                setattr(paths.SETTINGS, key, value)

    def test_atmos_stream_adds_identifying_suffix_to_default_track_filename(self):
        old_values = {
            "downloadPath": paths.SETTINGS.downloadPath,
            "trackFileFormat": paths.SETTINGS.trackFileFormat,
            "audioQuality": paths.SETTINGS.audioQuality,
        }
        stream = self._stream()
        stream.codec = "ec-3"
        stream.soundQuality = "DOLBY_ATMOS"
        try:
            paths.SETTINGS.downloadPath = "/tmp/tidekeeper"
            paths.SETTINGS.trackFileFormat = "{TrackNumber} - {ArtistName} - {TrackTitle}{ExplicitFlag}"
            paths.SETTINGS.audioQuality = AudioQuality.Atmos

            track_path = paths.getTrackPath(self._track(), stream, self._album())

            self.assertTrue(track_path.endswith("01 - Artist - Track [Dolby Atmos].m4a"))
        finally:
            for key, value in old_values.items():
                setattr(paths.SETTINGS, key, value)

    def test_track_path_supports_stream_quality_and_codec_tokens(self):
        old_values = {
            "downloadPath": paths.SETTINGS.downloadPath,
            "trackFileFormat": paths.SETTINGS.trackFileFormat,
            "audioQuality": paths.SETTINGS.audioQuality,
        }
        stream = self._stream()
        stream.codec = "ec-3"
        stream.soundQuality = "DOLBY_ATMOS"
        try:
            paths.SETTINGS.downloadPath = "/tmp/tidekeeper"
            paths.SETTINGS.trackFileFormat = "{TrackTitle} [{StreamQuality}] [{Codec}]"
            paths.SETTINGS.audioQuality = AudioQuality.Atmos

            track_path = paths.getTrackPath(self._track(), stream, self._album())

            self.assertTrue(track_path.endswith("Track [Dolby Atmos] [ec-3].m4a"))
        finally:
            for key, value in old_values.items():
                setattr(paths.SETTINGS, key, value)

    def test_metadata_falls_back_when_artists_is_missing(self):
        """Issue #38: TIDAL omits `artists`, so aigpy sets the attribute to None."""
        track = self._track()
        album = self._album()
        track.album = album
        track.artists = None
        album.artists = None
        track.copyRight = "Copyright"
        track.isrc = "ISRC"
        fake_tag = SimpleNamespace(save=mock.Mock(return_value=True))

        with mock.patch.object(download.aigpy.tag, "TagTool", return_value=fake_tag), \
             mock.patch.object(download.TIDAL_API, "getCoverUrl", return_value=""):
            download.__setMetaData__(track, album, "/tmp/track.m4a", None, "")

        self.assertEqual(fake_tag.artist, ["Artist"])
        self.assertEqual(fake_tag.albumartist, ["Artist"])

    def test_metadata_uses_every_artist_name(self):
        track = self._track()
        album = self._album()
        track.album = album
        track.artists = [self._artist("Artist One", 1), self._artist("Artist Two", 2)]
        album.artists = [self._artist("Artist One", 1), self._artist("Artist Three", 3)]
        track.copyRight = "Copyright"
        track.isrc = "ISRC"
        fake_tag = SimpleNamespace(save=mock.Mock(return_value=True))

        with mock.patch.object(download.aigpy.tag, "TagTool", return_value=fake_tag), \
             mock.patch.object(download.TIDAL_API, "getCoverUrl", return_value=""):
            download.__setMetaData__(track, album, "/tmp/track.m4a", None, "")

        self.assertEqual(fake_tag.artist, ["Artist One", "Artist Two"])
        self.assertEqual(fake_tag.albumartist, ["Artist One", "Artist Three"])

    def test_artist_helpers_tolerate_non_list_artists(self):
        """Album/track models default to a prototype instance, not a list."""
        api = TidalAPI()

        for artists in (None, Artist(), "unexpected"):
            self.assertEqual(api.getArtistsID(artists), "")
            self.assertEqual(api.getArtistsName(artists), "")

        self.assertEqual(api.getArtistsName([self._artist("Artist One", 1)]), "Artist One")
        self.assertEqual(api.getArtistsID([self._artist("Artist One", 1)]), "1")

    def test_album_path_handles_missing_artist_list(self):
        album = self._album()
        album.artists = None
        old_format = paths.SETTINGS.albumFolderFormat
        try:
            paths.SETTINGS.albumFolderFormat = "{ArtistName}-{ArtistID}-{AlbumTitle}"
            self.assertTrue(paths.getAlbumPath(album).endswith("--Album"))
        finally:
            paths.SETTINGS.albumFolderFormat = old_format

    def test_metadata_save_failure_is_reported(self):
        track = self._track()
        album = self._album()
        track.album = album
        track.copyRight = "Copyright"
        track.isrc = "ISRC"
        fake_tag = SimpleNamespace(save=mock.Mock(return_value=(False, "tag write failed")))

        with mock.patch.object(download.aigpy.tag, "TagTool", return_value=fake_tag), \
             mock.patch.object(download.TIDAL_API, "getCoverUrl", return_value=""):
            with self.assertRaisesRegex(Exception, "tag write failed"):
                download.__setMetaData__(track, album, "/tmp/track.m4a", None, "")

    def test_metadata_tags_are_created_before_save_when_missing(self):
        track = self._track()
        album = self._album()
        track.album = album
        track.copyRight = "Copyright"
        track.isrc = "ISRC"
        fake_handle = SimpleNamespace(tags=None, add_tags=mock.Mock())
        fake_tag = SimpleNamespace(_handle=fake_handle, save=mock.Mock(return_value=True))

        with mock.patch.object(download.aigpy.tag, "TagTool", return_value=fake_tag), \
             mock.patch.object(download.TIDAL_API, "getCoverUrl", return_value=""):
            download.__setMetaData__(track, album, "/tmp/track.m4a", None, "")

        fake_handle.add_tags.assert_called_once_with()
        fake_tag.save.assert_called_once_with("")

    def test_failed_track_log_is_reusable_as_link_file(self):
        old_download_path = download.SETTINGS.downloadPath
        track = self._track()
        album = self._album()
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                download.SETTINGS.downloadPath = temp_dir
                with mock.patch.object(download.TIDAL_API, "getStreamUrlByPriority", side_effect=Exception("HTTP 429")):
                    ok, msg = download.downloadTrack(track, album)

                failed_log = Path(temp_dir) / "failed-tracks.txt"
                self.assertFalse(ok)
                self.assertIn("HTTP 429", msg)
                self.assertTrue(failed_log.exists())
                lines = failed_log.read_text(encoding="utf-8").splitlines()
                retry_urls = [line for line in lines if line and not line.startswith("#")]
                self.assertEqual(retry_urls, ["https://tidal.com/browse/track/456"])
                self.assertTrue(any("Track" in line and "HTTP 429" in line for line in lines))
            finally:
                download.SETTINGS.downloadPath = old_download_path

    def test_atmos_client_not_entitled_falls_back_to_max_stream(self):
        api = TidalAPI()
        manifest = base64.b64encode(json.dumps({
            "codecs": "flac",
            "urls": ["https://example.invalid/fallback.flac"],
            "mimeType": "audio/flac",
        }).encode("utf-8")).decode("utf-8")

        with mock.patch.object(
            api,
            "__getOpenApiTrackManifest__",
            side_effect=Exception(
                'Track manifest request failed: HTTP 403 {"errors":[{"code":"CLIENT_NOT_ENTITLED"}]}'
            ),
        ), mock.patch.object(api, "__getPlaybackData__", return_value={
            "trackid": 456,
            "audioQuality": "HI_RES",
            "manifestMimeType": "application/vnd.tidal.bt",
            "manifest": manifest,
        }) as fallback_get:
            stream = api.getStreamUrl(456, AudioQuality.Atmos)

        self.assertEqual(stream.soundQuality, "HI_RES")
        self.assertEqual(stream.url, "https://example.invalid/fallback.flac")
        fallback_get.assert_any_call(456, _playback_params("HI_RES"))

    def test_blocked_max_stream_falls_back_to_legacy_hi_res_stream(self):
        api = TidalAPI()
        manifest = base64.b64encode(json.dumps({
            "codecs": "flac",
            "urls": ["https://example.invalid/hires.flac"],
            "mimeType": "audio/flac",
        }).encode("utf-8")).decode("utf-8")

        blocked = TidalApiError(
            'Get operation failed: HTTP 403 {"errors":[{"code":"CLIENT_NOT_ENTITLED"}]}',
            403,
            ["CLIENT_NOT_ENTITLED"],
        )

        with mock.patch.object(api, "__getOpenApiTrackManifest__", side_effect=blocked), \
             mock.patch.object(api, "__getPlaybackData__", side_effect=[
                blocked,
                {
                    "trackid": 456,
                    "audioQuality": "HI_RES",
                    "manifestMimeType": "application/vnd.tidal.bt",
                    "manifest": manifest,
                },
            ]) as get:
            stream = api.getStreamUrl(456, AudioQuality.Max)

        self.assertEqual(stream.soundQuality, "HI_RES")
        self.assertEqual(stream.url, "https://example.invalid/hires.flac")
        self.assertEqual(stream.requestedQuality, "Max")
        self.assertEqual(stream.fallbackQuality, "Master")
        self.assertEqual(stream.fallbackReason, "requested format is not allowed for this account or track")
        self.assertIn("CLIENT_NOT_ENTITLED", stream.fallbackError)
        self.assertEqual(
            get.call_args_list,
            [
                mock.call(456, _playback_params("HI_RES_LOSSLESS")),
                mock.call(456, _playback_params("HI_RES")),
            ],
        )

    def test_standard_api_quality_mismatch_falls_through_to_openapi_flac(self):
        """Issue #32: standard playback API returns HIGH when LOSSLESS was
        requested.  The OpenAPI FLAC endpoint should be tried before giving up."""
        api = TidalAPI()

        # Standard playback API returns HIGH (wrong quality).
        high_manifest = base64.b64encode(json.dumps({
            "codecs": "aac",
            "urls": ["https://example.invalid/high.m4a"],
            "mimeType": "audio/mp4",
        }).encode("utf-8")).decode("utf-8")

        # OpenAPI FLAC endpoint returns LOSSLESS (correct quality).
        flac_xml = self._dash_manifest("flac")
        flac_uri = "data:application/dash+xml;base64," + base64.b64encode(
            flac_xml.encode("utf-8")
        ).decode("utf-8")

        with mock.patch.object(api, "__getPlaybackData__", return_value={
            "trackid": 456,
            "audioQuality": "HIGH",
            "manifestMimeType": "application/vnd.tidal.bt",
            "manifest": high_manifest,
        }), mock.patch.object(api, "__getOpenApiTrackManifest__", return_value={
            "formats": ["FLAC"],
            "uri": flac_uri,
        }) as openapi_get:
            stream = api.getStreamUrlByPriority(456, [AudioQuality.HiFi])

        self.assertEqual(stream.soundQuality, "LOSSLESS")
        self.assertIn("flac", stream.codec.lower())
        openapi_get.assert_called_once()

    def test_settings_read_parses_audio_quality_priority(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "settings.json"
            settings_path.write_text(json.dumps({
                "audioQuality": "Atmos",
                "audioQualityPriority": ["Atmos", "High", "HiFi", "Normal"],
                "videoQuality": "P360",
            }), encoding="utf-8")

            settings = Settings()
            settings.read(str(settings_path))

        self.assertEqual(settings.audioQuality, AudioQuality.Atmos)
        self.assertEqual(settings.audioQualityPriority, [
            AudioQuality.Atmos,
            AudioQuality.High,
            AudioQuality.HiFi,
            AudioQuality.Normal,
        ])

    def test_audio_quality_priority_accepts_user_facing_aliases(self):
        settings = Settings()

        self.assertEqual(settings.getAudioQualityPriority(
            "Dolby Atmos,High (AAC 320),Lossless,Low (AAC 96)"
        ), [
            AudioQuality.Atmos,
            AudioQuality.High,
            AudioQuality.HiFi,
            AudioQuality.Normal,
        ])

    def test_settings_save_serializes_audio_quality_priority_names(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "settings.json"
            settings = Settings()
            settings.read(str(settings_path))
            settings.audioQuality = AudioQuality.Atmos
            settings.audioQualityPriority = [AudioQuality.Atmos, AudioQuality.High, AudioQuality.HiFi]
            settings.save()

            data = json.loads(settings_path.read_text(encoding="utf-8"))

        self.assertEqual(data["audioQuality"], "Atmos")
        self.assertEqual(data["audioQualityPriority"], ["Atmos", "High", "HiFi"])

    def test_audio_quality_priority_tries_high_before_lossless(self):
        api = TidalAPI()
        manifest = base64.b64encode(json.dumps({
            "codecs": "aac",
            "urls": ["https://example.invalid/fallback.m4a"],
            "mimeType": "audio/mp4",
        }).encode("utf-8")).decode("utf-8")

        with mock.patch.object(
            api,
            "__getOpenApiTrackManifest__",
            side_effect=Exception(
                'Track manifest request failed: HTTP 403 {"errors":[{"code":"CLIENT_NOT_ENTITLED"}]}'
            ),
        ), mock.patch.object(api, "__getPlaybackData__", return_value={
            "trackid": 456,
            "audioQuality": "HIGH",
            "manifestMimeType": "application/vnd.tidal.bt",
            "manifest": manifest,
        }) as fallback_get:
            stream = api.getStreamUrlByPriority(456, [
                "Atmos",
                "High",
                "HiFi",
                "Normal",
            ])

        self.assertEqual(stream.soundQuality, "HIGH")
        self.assertEqual(stream.url, "https://example.invalid/fallback.m4a")
        fallback_get.assert_any_call(456, _playback_params("HIGH"))

    def test_audio_quality_priority_rejects_lower_actual_quality_and_keeps_trying(self):
        api = TidalAPI()
        low_manifest = base64.b64encode(json.dumps({
            "codecs": "aac",
            "urls": ["https://example.invalid/low.m4a"],
            "mimeType": "audio/mp4",
        }).encode("utf-8")).decode("utf-8")
        lossless_uri = "data:application/dash+xml;base64," + base64.b64encode(
            self._dash_manifest("flac").encode("utf-8")
        ).decode("utf-8")

        with mock.patch.object(
            api,
            "__getOpenApiTrackManifest__",
            side_effect=[
                Exception(
                    'Track manifest request failed: HTTP 403 {"errors":[{"code":"CLIENT_NOT_ENTITLED"}]}'
                ),
                {
                    "formats": ["FLAC"],
                    "uri": lossless_uri,
                },
            ],
        ), mock.patch.object(api, "__getPlaybackData__", side_effect=[
            {
                "trackid": 456,
                "audioQuality": "LOW",
                "manifestMimeType": "application/vnd.tidal.bt",
                "manifest": low_manifest,
            },
            {
                "trackid": 456,
                "audioQuality": "LOW",
                "manifestMimeType": "application/vnd.tidal.bt",
                "manifest": low_manifest,
            },
        ]) as fallback_get:
            stream = api.getStreamUrlByPriority(456, [
                "Atmos",
                "High",
                "Lossless",
                "Low",
            ])

        self.assertEqual(stream.soundQuality, "LOSSLESS")
        self.assertEqual(stream.url, "https://example.invalid/init.mp4")
        self.assertEqual(stream.requestedQuality, "Dolby Atmos")
        self.assertEqual(stream.fallbackQuality, "HiFi")
        fallback_get.assert_any_call(456, _playback_params("HIGH"))

    def test_hifi_stream_uses_openapi_flac_manifest(self):
        api = TidalAPI()
        uri = "data:application/dash+xml;base64," + base64.b64encode(
            self._dash_manifest("flac").encode("utf-8")
        ).decode("utf-8")

        with mock.patch.object(api, "__getOpenApiTrackManifest__", return_value={
            "formats": ["FLAC"],
            "uri": uri,
        }) as openapi_get, mock.patch.object(
            api,
            "__getPlaybackData__",
            side_effect=Exception("Get operation err!Asset is not ready for playback"),
        ) as playback_get:
            stream = api.getStreamUrlByPriority(456, [AudioQuality.HiFi])

        self.assertEqual(stream.soundQuality, "LOSSLESS")
        self.assertEqual(stream.codec, "flac")
        self.assertEqual(stream.container, "mp4")
        self.assertEqual(stream.url, "https://example.invalid/init.mp4")
        self.assertEqual(stream.urls, [
            "https://example.invalid/init.mp4",
            "https://example.invalid/1.mp4",
            "https://example.invalid/2.mp4",
        ])
        playback_get.assert_called_once_with(456, _playback_params("LOSSLESS"))
        openapi_get.assert_called_once_with(456, ["FLAC"])

    def test_max_openapi_fallback_requests_flac_hires(self):
        api = TidalAPI()
        uri = "data:application/dash+xml;base64," + base64.b64encode(
            self._dash_manifest("flac").encode("utf-8")
        ).decode("utf-8")

        with mock.patch.object(api, "__getOpenApiTrackManifest__", return_value={
            "formats": ["FLAC_HIRES", "FLAC"],
            "uri": uri,
        }) as openapi_get, mock.patch.object(
            api,
            "__getPlaybackData__",
            side_effect=Exception("Get operation err!Asset is not ready for playback"),
        ):
            stream = api.getStreamUrlByPriority(456, [AudioQuality.Max])

        self.assertEqual(stream.soundQuality, "HI_RES_LOSSLESS")
        openapi_get.assert_called_once_with(456, ["FLAC_HIRES", "FLAC"])

    def test_openapi_manifest_falls_back_from_download_to_playback_usage(self):
        api = TidalAPI()
        payload = {"data": {"attributes": {"formats": ["FLAC"], "uri": "data:x,eyJ0ZXN0In0="}}}

        def fake_once(track_id, formats, usage):
            if usage == "DOWNLOAD":
                raise TidalApiError("Track manifest request failed: HTTP 403", statusCode=403)
            return payload["data"]["attributes"]

        with mock.patch.object(api, "__getOpenApiTrackManifestOnce__", side_effect=fake_once) as once_get:
            attrs = api.__getOpenApiTrackManifest__(456, ["FLAC"])

        self.assertEqual(attrs["formats"], ["FLAC"])
        self.assertEqual(once_get.call_count, 2)
        once_get.assert_any_call(456, ["FLAC"], "DOWNLOAD")
        once_get.assert_any_call(456, ["FLAC"], "PLAYBACK")

    def test_download_track_uses_configured_audio_quality_priority(self):
        old_priority = download.SETTINGS.audioQualityPriority
        old_quality = download.SETTINGS.audioQuality
        track = self._track()
        try:
            download.SETTINGS.audioQuality = AudioQuality.Atmos
            download.SETTINGS.audioQualityPriority = [AudioQuality.Atmos, AudioQuality.High]
            expected_stream = self._stream()
            with mock.patch.object(
                download.TIDAL_API,
                "getStreamUrlByPriority",
                return_value=expected_stream,
            ) as priority_get:
                stream = download.__getTrackStream__(track.id)

            self.assertIs(stream, expected_stream)
            priority_get.assert_called_once_with(track.id, [AudioQuality.Atmos, AudioQuality.High])
        finally:
            download.SETTINGS.audioQualityPriority = old_priority
            download.SETTINGS.audioQuality = old_quality

    def test_download_track_uses_single_quality_as_strict_priority(self):
        old_priority = download.SETTINGS.audioQualityPriority
        old_quality = download.SETTINGS.audioQuality
        track = self._track()
        try:
            download.SETTINGS.audioQuality = AudioQuality.HiFi
            download.SETTINGS.audioQualityPriority = []
            expected_stream = self._stream()
            with mock.patch.object(
                download.TIDAL_API,
                "getStreamUrlByPriority",
                return_value=expected_stream,
            ) as priority_get, mock.patch.object(download.TIDAL_API, "getStreamUrl") as ladder_get:
                stream = download.__getTrackStream__(track.id)

            self.assertIs(stream, expected_stream)
            priority_get.assert_called_once_with(track.id, [AudioQuality.HiFi])
            ladder_get.assert_not_called()
        finally:
            download.SETTINGS.audioQualityPriority = old_priority
            download.SETTINGS.audioQuality = old_quality

    def test_quality_priority_command_sets_fallback_order(self):
        old_argv = sys.argv
        old_quality = tidal_dl.SETTINGS.audioQuality
        old_priority = tidal_dl.SETTINGS.audioQualityPriority
        sys.argv = ["tidekeeper", "--quality-priority", "Atmos,High,HiFi,Normal"]
        try:
            with mock.patch.object(tidal_dl.aigpy.path, "mkdirs", return_value=True), \
                 mock.patch.object(tidal_dl.SETTINGS, "save") as save:
                tidal_dl.mainCommand()

            self.assertEqual(tidal_dl.SETTINGS.audioQuality, AudioQuality.Atmos)
            self.assertEqual(tidal_dl.SETTINGS.audioQualityPriority, [
                AudioQuality.Atmos,
                AudioQuality.High,
                AudioQuality.HiFi,
                AudioQuality.Normal,
            ])
            save.assert_called()
        finally:
            sys.argv = old_argv
            tidal_dl.SETTINGS.audioQuality = old_quality
            tidal_dl.SETTINGS.audioQualityPriority = old_priority

    def test_quality_command_clears_fallback_order(self):
        old_argv = sys.argv
        old_quality = tidal_dl.SETTINGS.audioQuality
        old_priority = tidal_dl.SETTINGS.audioQualityPriority
        sys.argv = ["tidekeeper", "--quality", "High"]
        try:
            tidal_dl.SETTINGS.audioQualityPriority = [AudioQuality.Atmos, AudioQuality.High]
            with mock.patch.object(tidal_dl.aigpy.path, "mkdirs", return_value=True), \
                 mock.patch.object(tidal_dl.SETTINGS, "save"):
                tidal_dl.mainCommand()

            self.assertEqual(tidal_dl.SETTINGS.audioQuality, AudioQuality.High)
            self.assertEqual(tidal_dl.SETTINGS.audioQualityPriority, [])
        finally:
            sys.argv = old_argv
            tidal_dl.SETTINGS.audioQuality = old_quality
            tidal_dl.SETTINGS.audioQualityPriority = old_priority

    def test_get_playback_data_tries_v4_before_legacy(self):
        api = TidalAPI()
        manifest = {
            "trackid": 123,
            "audioQuality": "HIGH",
            "manifestMimeType": "application/vnd.tidal.bt",
            "manifest": base64.b64encode(json.dumps({
                "codecs": "aac",
                "urls": ["https://example.invalid/track.m4a"],
                "mimeType": "audio/mp4",
            }).encode("utf-8")).decode("utf-8"),
        }
        calls = []

        def fake_get_once(path, params, base):
            calls.append((base, path))
            if path.endswith("/v4"):
                raise Exception("v4 unavailable")
            return manifest

        with mock.patch.object(api, "__getOnce__", side_effect=fake_get_once):
            data = api.__getPlaybackData__(123, _playback_params("HIGH", prefetch=True))

        self.assertEqual(data["trackid"], 123)
        self.assertEqual(calls[0][1], "tracks/123/playbackinfopostpaywall/v4")
        self.assertEqual(calls[1][1], "tracks/123/playbackinfopostpaywall")

    def test_download_rejects_track_not_stream_ready(self):
        track = self._track()
        track.streamReady = False
        with mock.patch.object(download, "__getTrackStream__") as get_stream:
            ok, err = download.downloadTrack(track)
        get_stream.assert_not_called()
        self.assertFalse(ok)
        self.assertIn("not ready for streaming", err)

    def test_download_error_hint_for_asset_not_ready(self):
        hint = download.__downloadErrorHint__(Exception("Asset is not ready for playback"))
        self.assertIn("retry later", hint)

    def test_tidal_url_parser_ignores_query_strings_and_fragments(self):
        api = TidalAPI()

        etype, sid = api.parseUrl("https://tidal.com/browse/track/70973230?u=1#play")

        self.assertEqual(etype, Type.Track)
        self.assertEqual(sid, "70973230")

    def test_tidal_url_parser_handles_nested_paths(self):
        api = TidalAPI()

        etype, sid = api.parseUrl("https://tidal.com/browse/album/123/track/456")

        self.assertEqual(etype, Type.Track)
        self.assertEqual(sid, "456")

    @unittest.skipIf(sys.platform.startswith("win"), "POSIX file mode check")
    def test_token_save_restricts_file_permissions(self):
        token = events.TokenSettings()
        token.accessToken = "access"
        token.refreshToken = "refresh"
        with tempfile.TemporaryDirectory() as temp_dir:
            token.read(str(Path(temp_dir) / "token.json"))
            token.save()

            mode = Path(token._path_).stat().st_mode & 0o777

        self.assertEqual(mode, 0o600)

    def test_api_get_recovers_stale_client_404_by_refreshing_token(self):
        api = TidalAPI()
        api.key.accessToken = "stale-access"
        api.key.countryCode = "GB"

        stale_body = {
            "status": 404,
            "subStatus": 4022,
            "userMessage": "Client referenced in the request does not seem to exist.",
        }

        def fake_response(status, body):
            return SimpleNamespace(
                status_code=status,
                text=json.dumps(body),
                headers={},
                close=mock.Mock(),
                json=mock.Mock(return_value=body),
            )

        def fake_refresh():
            api.key.accessToken = "fresh-access"
            return True

        with mock.patch.object(api, "__refreshSavedAccessToken__", side_effect=fake_refresh), \
             mock.patch.object(api.session, "get", side_effect=[
                 fake_response(404, stale_body),
                 fake_response(200, {"id": 123, "title": "Album"}),
             ]) as get:
            data = api.__get__("albums/123")

        self.assertEqual(data["title"], "Album")
        self.assertEqual(get.call_args_list[0].kwargs["headers"]["authorization"], "Bearer stale-access")
        self.assertEqual(get.call_args_list[1].kwargs["headers"]["authorization"], "Bearer fresh-access")

    def test_api_get_stale_client_404_raises_relogin_error_when_refresh_fails(self):
        api = TidalAPI()
        api.key.accessToken = "stale-access"
        api.key.countryCode = "GB"

        stale_body = {
            "status": 404,
            "subStatus": 4022,
            "userMessage": "Client referenced in the request does not seem to exist.",
        }
        response = SimpleNamespace(
            status_code=404,
            text=json.dumps(stale_body),
            headers={},
            close=mock.Mock(),
            json=mock.Mock(return_value=stale_body),
        )

        old_delay = events.SETTINGS.downloadDelay
        try:
            events.SETTINGS.downloadDelay = False
            with mock.patch.object(api, "__refreshSavedAccessToken__", return_value=False), \
                 mock.patch.object(api.session, "get", return_value=response) as get_mock:
                with self.assertRaises(TidalApiError) as ctx:
                    api.__getOnce__(
                        "tracks/456/playbackinfopostpaywall/v4",
                        _playback_params("LOSSLESS"),
                        API_BASE_PRIMARY,
                    )
        finally:
            events.SETTINGS.downloadDelay = old_delay

        self.assertIn("log in again", str(ctx.exception))
        self.assertIn("4022", ctx.exception.errorCodes)
        self.assertEqual(get_mock.call_count, 1)

    def test_openapi_manifest_prerequisite_missing_retries_with_base_format(self):
        api = TidalAPI()
        payload = {"formats": ["FLAC"], "uri": "data:x,eyJ0ZXN0In0="}

        def fake_once(track_id, formats, usage):
            if "FLAC_HIRES" in formats:
                raise TidalApiError(
                    'Track manifest request failed: HTTP 403 '
                    '{"errors":[{"status":"403","code":"PREREQUISITE_MISSING"}]}',
                    403,
                    ["PREREQUISITE_MISSING"],
                )
            return payload

        with mock.patch.object(api, "__getOpenApiTrackManifestOnce__", side_effect=fake_once) as once_get:
            attrs = api.__getOpenApiTrackManifest__(456, ["FLAC_HIRES", "FLAC"])

        self.assertEqual(attrs["formats"], ["FLAC"])
        once_get.assert_any_call(456, ["FLAC_HIRES", "FLAC"], "DOWNLOAD")
        once_get.assert_any_call(456, ["FLAC"], "DOWNLOAD")

    def test_track_specific_403_does_not_block_playback_api_for_session(self):
        api = TidalAPI()

        prerequisite_error = TidalApiError(
            "Get operation failed: HTTP 403", 403, ["PREREQUISITE_MISSING"]
        )
        api.__markPlaybackParamBlocked__("HI_RES_LOSSLESS", prerequisite_error)
        self.assertNotIn("HI_RES_LOSSLESS", api._playbackBlockedParams)

        stale_error = TidalApiError("Get operation failed: HTTP 404", 404, ["4022"])
        api.__markPlaybackParamBlocked__("LOW", stale_error)
        self.assertNotIn("LOW", api._playbackBlockedParams)

        entitlement_error = TidalApiError(
            "Get operation failed: HTTP 403", 403, ["CLIENT_NOT_ENTITLED"]
        )
        api.__markPlaybackParamBlocked__("HI_RES_LOSSLESS", entitlement_error)
        self.assertIn("HI_RES_LOSSLESS", api._playbackBlockedParams)

    def test_download_error_hint_for_stale_session(self):
        hint = download.__downloadErrorHint__(Exception(
            'Get operation failed: HTTP 404 {"status":404,"subStatus":4022,'
            '"userMessage":"Client referenced in the request does not seem to exist."}'
        ))
        self.assertIn("log in again", hint)

    def test_download_error_hint_for_prerequisite_missing(self):
        hint = download.__downloadErrorHint__(Exception(
            'Track manifest request failed: HTTP 403 '
            '{"errors":[{"status":"403","code":"PREREQUISITE_MISSING"}]}'
        ))
        self.assertIn("quality-priority", hint)


if __name__ == "__main__":
    unittest.main()
