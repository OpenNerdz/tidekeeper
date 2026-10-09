"""Desktop backend: search, queue persistence, and settings reload."""

import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tidal_dl import events
from tidal_dl.enums import Type
from tidal_dl.gui_app.backend import SearchItem, TidekeeperBackend, queue_item, to_search_item, with_video_only
from tidal_dl.paths import PATHS
from tidal_dl.settings import SETTINGS
from tidal_dl.tidal import TIDAL_API

from fixtures import CatalogFixtures, ProfileFixture, TransferFixture


class DesktopBackendTests(unittest.TestCase):
    def test_folder_names_are_searched_instead_of_queued_as_links(self):
        from tidal_dl.enums import Type
        from tidal_dl.gui_app.backend import TidekeeperBackend

        backend = TidekeeperBackend()
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(backend, "_ensure_catalog_session"), \
                mock.patch("tidal_dl.gui_app.backend.TIDAL_API.searchAll", return_value=None) as search:
            self.assertEqual(backend.search(directory, Type.Track), [])
            search.assert_called_once()
            list_file = Path(directory) / "links.txt"
            list_file.write_text("https://tidal.com/browse/track/1\n", encoding="utf-8")
            [item] = backend.search(str(list_file), Type.Track)
        self.assertEqual((item.kind, item.title), (Type.Null, "links.txt"))

    def test_session_expiry_text_reads_naturally(self):
        import time
        from tidal_dl.gui_app.backend import AuthStatus

        self.assertEqual(AuthStatus("1", "US", 0, True).expiry_summary, "expiry unknown")
        self.assertEqual(AuthStatus("1", "US", time.time() - 5, True).expiry_summary, "session expired")
        self.assertTrue(AuthStatus("1", "US", time.time() + 7200, True).expiry_summary.startswith("expires in 1h"))

    def test_search_titles_include_the_track_version(self):
        def track(version):
            return SimpleNamespace(id=1, title="Strobe", version=version, artists=[], duration=0)

        self.assertEqual(to_search_item(Type.Track, track("Extended Mix")).title, "Strobe (Extended Mix)")
        self.assertEqual(to_search_item(Type.Track, track(None)).title, "Strobe")
        self.assertEqual(to_search_item(Type.Track, track("  ")).title, "Strobe")


class QueuePersistenceTests(TransferFixture, unittest.TestCase):
    def test_requeue_creates_independent_state_and_source(self):
        source = SearchItem(Type.Track, 'Song', '', '', '1', '', SimpleNamespace(id=1), status='Done')
        first, second = queue_item(source), queue_item(source)
        first.status = 'Failed'
        first.source.id = 2
        self.assertEqual(second.status, 'Queued')
        self.assertEqual(source.status, 'Done')
        self.assertEqual(second.source.id, 1)
        self.assertEqual(len({first.job_id, second.job_id, source.job_id}), 3)

    def test_queue_roundtrip_restores_interrupted_jobs(self):
        item = SearchItem(Type.Track, 'Song', '', '', '1', '', SimpleNamespace(id=1), status='Downloading')
        backend = TidekeeperBackend()
        with mock.patch.object(PATHS, 'getConfigDirectory', return_value=str(self.root)):
            backend.save_queue([item])
            restored = backend.load_queue()
        self.assertEqual(restored[0].status, 'Interrupted')
        self.assertEqual(restored[0].identifier, '1')
        self.assertIsNone(restored[0].source)
        self.assertIn('Resume', restored[0].status_detail)
        self.assertEqual((self.root / '.tidekeeper-queue.json').stat().st_mode & 0o777, 0o600)

    def test_queue_persists_bounded_redacted_failure_details(self):
        item = SearchItem(Type.Track, 'Song', '', '', '1', '', None, status='Failed',
                          status_detail='access_token=dummy-secret Could not load stream. ' + 'x' * 3000)
        backend = TidekeeperBackend()
        with mock.patch.object(PATHS, 'getConfigDirectory', return_value=str(self.root)):
            backend.save_queue([item])
            restored = backend.load_queue()
        self.assertEqual(restored[0].status, 'Failed')
        self.assertIn('Could not load stream', restored[0].status_detail)
        self.assertLessEqual(len(restored[0].status_detail), 2000)
        self.assertNotIn('dummy-secret', (self.root / '.tidekeeper-queue.json').read_text())


class SettingsReloadTests(ProfileFixture, unittest.TestCase):
    def test_reload_restores_saved_settings_without_persisting_runtime_changes(self):
        from tidal_dl.paths import PATHS
        profile = self.root / 'settings.json'
        profile.write_text(json.dumps({'multiThread': False, 'apiKeyIndex': SETTINGS.apiKeyIndex}))
        SETTINGS.multiThread = True
        with mock.patch.object(PATHS, 'getProfilePath', return_value=str(profile)), \
             mock.patch.object(TIDAL_API, 'apiKey', TIDAL_API.apiKey), \
             mock.patch('tidal_dl.gui_app.backend.logout') as logout:
            self.assertFalse(TidekeeperBackend().reload_settings()['reauth_required'])
            self.assertFalse(SETTINGS.multiThread)
            logout.assert_not_called()

    def test_reload_during_download_is_rejected(self):
        backend = TidekeeperBackend()
        backend._download_active = True
        with self.assertRaisesRegex(RuntimeError, 'active download'):
            backend.reload_settings()


class DesktopBackendCatalogTests(CatalogFixtures, unittest.TestCase):
    def test_gui_backend_syncs_saved_country_code_before_search(self):
        old_values = {
            "userid": events.TOKEN.userid,
            "countryCode": events.TOKEN.countryCode,
            "clientId": events.TOKEN.clientId,
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
            "clientId": events.TOKEN.clientId,
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
             mock.patch.object(events.TIDAL_API, "searchAll", return_value=object()), \
             mock.patch.object(events.TIDAL_API, "getSearchResultItems", side_effect=fake_items):
            items = backend.search("midnight", Type.Null)

        self.assertEqual([item.kind for item in items], [Type.Artist, Type.Album, Type.Track])
        self.assertEqual([item.title for item in items], ["Artist", "Album", "Track"])

    def test_gui_backend_album_search_uses_artist_discography(self):
        backend = TidekeeperBackend()
        buried = self._album()
        buried.title = "Masz to jak w Banku"
        with mock.patch.object(backend, "_ensure_catalog_session"), \
             mock.patch.object(events.TIDAL_API, "searchAlbumsForQuery", return_value=[buried]) as lookup:
            items = backend.search("O.S.T.R.", Type.Album)

        lookup.assert_called_once_with("O.S.T.R.", includeEP=events.SETTINGS.includeEP)
        self.assertEqual([item.title for item in items], ["Masz to jak w Banku"])
        self.assertEqual(items[0].kind, Type.Album)


if __name__ == "__main__":
    unittest.main()
