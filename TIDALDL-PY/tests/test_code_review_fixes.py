import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tidal_dl import download, events, printf
from tidal_dl.enums import Type
from tidal_dl.model import Album, Track
from tidal_dl.settings import SETTINGS, TOKEN
from tidal_dl.tidal import TidalAPI

try:
    from PySide6.QtWidgets import QApplication
except ImportError:  # pragma: no cover - GUI extra not installed
    QApplication = None


def _track(title, number, volume):
    track = Track()
    track.title = title
    track.trackNumber = number
    track.volumeNumber = volume
    return track


class AlbumInfoTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        patcher = mock.patch.multiple(SETTINGS, downloadPath=self.directory.name, albumFolderFormat="{AlbumTitle}")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _album(self, volumes):
        album = Album()
        album.id = 7
        album.title = "Album"
        album.numberOfVolumes = volumes
        return album

    def _info(self):
        return (Path(self.directory.name) / "Album" / "AlbumInfo.txt").read_text(encoding="utf-8")

    def test_missing_volume_count_still_lists_every_track(self):
        for volumes in (None, 0):
            with self.subTest(volumes=volumes):
                tracks = [_track("One", 1, 1), _track("Two", 1, 2)]
                self.assertTrue(download.downloadAlbumInfo(self._album(volumes), tracks))
                info = self._info()
                self.assertIn("CD 2", info)
                self.assertIn("One", info)
                self.assertIn("Two", info)

    def test_write_failure_is_reported_without_aborting_the_album(self):
        with mock.patch.object(download, "__writeTextFile__", side_effect=PermissionError("denied")), \
                mock.patch.object(download.Printf, "err") as err:
            self.assertFalse(download.downloadAlbumInfo(self._album(1), [_track("One", 1, 1)]))
        self.assertIn("AlbumInfo.txt", err.call_args[0][0])


class PrintfLockTests(unittest.TestCase):
    def test_failed_console_write_releases_the_lock(self):
        failure = UnicodeEncodeError("ascii", "x", 0, 1, "unencodable")
        for method in (printf.Printf.err, printf.Printf.info, printf.Printf.success):
            with self.subTest(method=method.__name__):
                with mock.patch.object(printf, "print", side_effect=failure):
                    with self.assertRaises(UnicodeEncodeError):
                        method("message")
                self.assertFalse(printf.print_mutex.locked())


class ParseUrlTests(unittest.TestCase):
    def test_host_match_is_case_insensitive(self):
        api = TidalAPI()
        self.assertEqual(api.parseUrl("https://TIDAL.com/browse/album/123"), (Type.Album, "123"))
        self.assertEqual(api.parseUrl("12345"), (Type.Null, "12345"))


class LanguageSettingTests(unittest.TestCase):
    def setUp(self):
        self.saved = copy.deepcopy(SETTINGS.__dict__)
        self.addCleanup(self._restore)

    def _restore(self):
        SETTINGS.__dict__.clear()
        SETTINGS.__dict__.update(self.saved)
        events.LANG.setLang(SETTINGS.language)

    def _change(self, language):
        with mock.patch.object(events.Printf, "settings"), \
                mock.patch.object(events.Printf, "enterBool", return_value=False), \
                mock.patch.object(events.Printf, "enter", side_effect=["3", language]), \
                mock.patch.object(events.Printf, "info"), \
                mock.patch.object(SETTINGS, "save"):
            events.changeSettings()

    def test_language_is_stored_as_an_index(self):
        SETTINGS.language = 0
        self._change("2")
        self.assertEqual(SETTINGS.language, 2)

    def test_invalid_language_keeps_the_current_choice(self):
        SETTINGS.language = 1
        for value in ("abc", "999", "", "-1"):
            with self.subTest(value=value):
                self._change(value)
                self.assertEqual(SETTINGS.language, 1)


class TokenPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.saved = copy.deepcopy(TOKEN.__dict__)
        self.addCleanup(lambda: (TOKEN.__dict__.clear(), TOKEN.__dict__.update(self.saved)))

    def test_save_key_to_token_writes_every_session_field(self):
        api = TidalAPI()
        api.apiKey = {"clientId": "client-a"}
        api.key.userId, api.key.countryCode = 42, "NL"
        api.key.accessToken, api.key.refreshToken = "access", "refresh"
        with mock.patch.object(TOKEN, "save") as save:
            api.saveKeyToToken(123.0)
        save.assert_called_once_with()
        self.assertEqual(
            (TOKEN.userid, TOKEN.countryCode, TOKEN.clientId, TOKEN.accessToken, TOKEN.refreshToken,
             TOKEN.expiresAfter),
            (42, "NL", "client-a", "access", "refresh", 123.0),
        )

    def test_manual_token_login_persists_session(self):
        api = TidalAPI()
        api.apiKey = {"clientId": "client-b"}

        def login(token, userid=None):
            api.key.userId, api.key.countryCode, api.key.accessToken = 9, "US", token

        with mock.patch.object(events, "TIDAL_API", api), \
                mock.patch.object(api, "loginByAccessToken", side_effect=login), \
                mock.patch.object(events.Printf, "enter", side_effect=["pasted-access", "pasted-refresh"]), \
                mock.patch.object(TOKEN, "save"):
            events.loginByAccessToken()
        self.assertEqual(
            (TOKEN.userid, TOKEN.countryCode, TOKEN.clientId, TOKEN.accessToken, TOKEN.refreshToken,
             TOKEN.expiresAfter),
            (9, "US", "client-b", "pasted-access", "pasted-refresh", 0),
        )

    def test_oauth_data_includes_secret_only_when_configured(self):
        api = TidalAPI()
        api.apiKey = {"clientId": "id", "clientSecret": "secret"}
        self.assertEqual(api.__oauthData__(grant_type="refresh_token"), {
            "client_id": "id", "grant_type": "refresh_token", "scope": "r_usr w_usr w_sub",
            "client_secret": "secret",
        })
        api.apiKey = {"clientId": "id", "clientSecret": ""}
        self.assertNotIn("client_secret", api.__oauthData__())


@unittest.skipIf(QApplication is None, "PySide6 is not installed")
class GuiDropAndDoctorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from tidal_dl.gui_app.backend import DemoBackend
        from tidal_dl.gui_app.main_window import FIND_MODE_LINKS, MainWindow

        self.saved = copy.deepcopy(SETTINGS.__dict__)
        backend = DemoBackend()
        backend.initialize()
        self.window = MainWindow(backend)
        self.links_mode = FIND_MODE_LINKS

    def tearDown(self):
        self.window.close()
        SETTINGS.__dict__.clear()
        SETTINGS.__dict__.update(self.saved)

    def test_dropped_urls_and_files_are_staged_in_links(self):
        from PySide6.QtCore import QMimeData, QUrl

        mime = QMimeData()
        mime.setUrls([QUrl("https://tidal.com/browse/album/1"), QUrl.fromLocalFile("/tmp/list.txt")])
        values = self.window.dropped_inputs(mime)
        self.assertEqual(values, ["https://tidal.com/browse/album/1", "/tmp/list.txt"])

        self.window.direct_text.setPlainText("123")
        self.window.append_direct_inputs(values)
        self.assertEqual(self.window.find_stack.currentIndex(), self.links_mode)
        self.assertEqual(self.window.direct_text.toPlainText().splitlines(),
                         ["123", "https://tidal.com/browse/album/1", "/tmp/list.txt"])
        self.assertEqual(self.window.queue, [])

    def test_dropped_plain_text_splits_lines_and_ignores_blank_payloads(self):
        from PySide6.QtCore import QMimeData

        mime = QMimeData()
        mime.setText(" 111 \n\n222\n")
        self.assertEqual(self.window.dropped_inputs(mime), ["111", "222"])
        self.assertEqual(self.window.dropped_inputs(QMimeData()), [])

    def test_doctor_button_is_disabled_until_the_check_finishes(self):
        started = []
        self.window.start_worker = lambda worker: started.append(worker)
        self.window.run_doctor()
        self.assertFalse(self.window.doctor_button.isEnabled())
        started[0].run()
        self.app.processEvents()
        self.assertTrue(self.window.doctor_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
