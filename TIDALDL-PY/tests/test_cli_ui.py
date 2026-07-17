import io
import sys
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest import mock

import tidal_dl
from tidal_dl import printf
from tidal_dl.printf import Printf
from tidal_dl.paths import PATHS


class CliUiTests(unittest.TestCase):
    def setUp(self):
        PATHS.homePathOverride = None

    def test_compact_help_uses_one_option_per_line(self):
        output = io.StringIO()

        with mock.patch.object(printf, "isTermux", return_value=True):
            with redirect_stdout(output):
                Printf.usage()

        text = output.getvalue()
        self.assertIn("-l, --link URL\n  Download URL/ID/file", text)
        self.assertIn("--update\n  Update terminal install", text)
        self.assertIn("--doctor\n  Check config, auth, and local tools", text)
        self.assertIn("--paths\n  Show download/config paths", text)
        self.assertIn("--video-only\n  Download videos only for URL/ID/file", text)
        self.assertNotIn("OPTION                  DESCRIPTION", text)

    def test_compact_dashboard_uses_one_command_per_line(self):
        output = io.StringIO()

        with mock.patch.object(printf, "isTermux", return_value=True):
            with redirect_stdout(output):
                Printf.dashboard()

        text = output.getvalue()
        self.assertIn("1 Login / refresh", text)
        self.assertIn("5 Quality", text)
        self.assertIn("9 Update", text)
        self.assertIn("clear / cls Clear screen", text)
        self.assertNotIn("1 Login/refresh   2 Logout", text)

    def test_compact_api_key_picker_uses_simple_lines(self):
        items = [
            {"valid": "False", "platform": "Old", "formats": "Normal/High"},
            {"valid": "True", "platform": "Tidekeeper OAuth", "formats": "Normal/High/HiFi/Master"},
        ]
        output = io.StringIO()

        with mock.patch.object(printf, "isTermux", return_value=True):
            with redirect_stdout(output):
                Printf.apikeys(items)

        text = output.getvalue()
        self.assertIn("Tidal clients", text)
        self.assertIn("0 old - Old", text)
        self.assertIn("1 OK - Tidekeeper OAuth", text)
        self.assertNotIn("+", text)

    def test_track_output_shows_quality_fallback(self):
        output = io.StringIO()
        track = SimpleNamespace(
            title="Track",
            id=456,
            album=SimpleNamespace(title="Album"),
            version=None,
            explicit=False,
            audioQuality="DOLBY_ATMOS",
        )
        stream = SimpleNamespace(
            soundQuality="HI_RES_LOSSLESS",
            codec="flac",
            requestedQuality="Dolby Atmos",
            fallbackQuality="Max",
            fallbackReason="requested format is unavailable",
            fallbackError="Dolby Atmos stream is not available for this track.",
        )

        with redirect_stdout(output):
            Printf.track(track, stream)

        text = output.getvalue()
        self.assertIn("Requested-Q", text)
        self.assertIn("Dolby Atmos", text)
        self.assertIn("Fallback", text)
        self.assertIn("Max (requested format is unavailable)", text)

    def test_update_choice_aliases(self):
        self.assertEqual(tidal_dl.normalizeChoice("update"), "9")
        self.assertEqual(tidal_dl.normalizeChoice("upgrade"), "9")

    def test_paths_flag_prints_paths_without_login(self):
        with mock.patch("sys.argv", ["tidekeeper", "--paths"]):
            with mock.patch.object(Printf, "paths") as paths:
                tidal_dl.mainCommand()

        paths.assert_called_once_with()

    def test_open_output_flag_uses_download_path(self):
        with mock.patch("sys.argv", ["tidekeeper", "--open-output"]):
            with mock.patch("tidal_dl.openPath", return_value="/tmp/downloads") as open_path:
                with mock.patch.object(Printf, "success") as success:
                    tidal_dl.mainCommand()

        open_path.assert_called_once_with(tidal_dl.SETTINGS.downloadPath)
        success.assert_called_once()

    def test_link_command_returns_after_download(self):
        old_argv = sys.argv
        sys.argv = ["tidekeeper", "--link", "123456"]
        try:
            with mock.patch.object(tidal_dl.aigpy.path, "mkdirs", return_value=True), \
                 mock.patch.object(tidal_dl, "loginByConfig", return_value=True), \
                 mock.patch.object(tidal_dl, "start", return_value=True) as start:
                handled = tidal_dl.mainCommand()
        finally:
            sys.argv = old_argv

        self.assertEqual(handled, 0)
        start.assert_called_once_with("123456", False)

    def test_link_command_returns_nonzero_on_download_failure(self):
        old_argv = sys.argv
        sys.argv = ["tidekeeper", "--link", "123456"]
        try:
            with mock.patch.object(tidal_dl.aigpy.path, "mkdirs", return_value=True), \
                 mock.patch.object(tidal_dl, "loginByConfig", return_value=True), \
                 mock.patch.object(tidal_dl, "start", return_value=False):
                code = tidal_dl.mainCommand()
        finally:
            sys.argv = old_argv

        self.assertEqual(code, 1)

    def test_link_command_returns_nonzero_when_login_fails(self):
        old_argv = sys.argv
        sys.argv = ["tidekeeper", "--link", "123456"]
        try:
            with mock.patch.object(tidal_dl.aigpy.path, "mkdirs", return_value=True), \
                 mock.patch.object(tidal_dl, "loginByConfig", return_value=False), \
                 mock.patch.object(tidal_dl, "loginByWeb", return_value=False), \
                 mock.patch.object(tidal_dl, "start") as start:
                code = tidal_dl.mainCommand()
        finally:
            sys.argv = old_argv

        self.assertEqual(code, 1)
        start.assert_not_called()

    def test_video_only_flag_is_passed_to_link_download(self):
        with mock.patch("sys.argv", ["tidekeeper", "--video-only", "-l", "artist-id"]):
            with mock.patch.object(tidal_dl.aigpy.path, "mkdirs", return_value=True), \
                 mock.patch.object(tidal_dl, "loginByConfig", return_value=True), \
                 mock.patch.object(tidal_dl.Printf, "info"), \
                 mock.patch.object(tidal_dl, "start") as start:
                tidal_dl.mainCommand()

        start.assert_called_once_with("artist-id", True)

    def test_default_config_path(self):
        assert(PATHS.__getHomePath__() == PATHS.__getDefaultHomePath__())

    def test_config_path_override_overrides_paths(self):
        with mock.patch("sys.argv", ["tidekeeper", "-c", "/home/user/tidekeeper/config"]):
            with mock.patch("tidal_dl.os.path.isdir") as mock_isdir:
                mock_isdir.return_value = True
                tidal_dl.preMainCommand()
        assert(PATHS.__getHomePath__() == "/home/user/tidekeeper/config")

    def test_config_path_requires_existing_directory(self):
        with mock.patch("sys.argv", ["tidekeeper", "-c", "/magic/config"]):
            with self.assertRaises(ValueError):
                tidal_dl.preMainCommand()

    def test_sys_argvs_prevent_entering_while_loop(self):
        with mock.patch("sys.argv", ["tidekeeper", "--paths"]):
            with mock.patch("tidal_dl.Printf.choices") as mock_choices:
                mock_choices.side_effect = KeyboardInterrupt
                tidal_dl.main()
        mock_choices.assert_not_called()

    def test_sys_argvs_enable_entering_while_loop(self):
        with mock.patch("sys.argv", ["tidekeeper", "-c", "/home/user/tidekeeper/config"]):
            with mock.patch("tidal_dl.os.path.isdir") as mock_isdir:
                mock_isdir.return_value = True
                with mock.patch("tidal_dl.loginByWeb"):
                    with mock.patch("tidal_dl.Printf.choices") as mock_choices:
                        mock_choices.side_effect = KeyboardInterrupt
                        with self.assertRaises(KeyboardInterrupt):
                            tidal_dl.main()
        mock_choices.assert_called()


if __name__ == "__main__":
    unittest.main()
