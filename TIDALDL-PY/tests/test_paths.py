import unittest
from unittest import mock

from tidal_dl.model import StreamUrl
from tidal_dl.paths import __getExtension__, PATHS, openPath


class PathTests(unittest.TestCase):
    def test_dash_flac_in_mp4_container_uses_m4a_extension(self):
        stream = StreamUrl()
        stream.url = "https://example.invalid/init.mp4"
        stream.codec = "flac"
        stream.manifestMimeType = "application/dash+xml"
        stream.container = "mp4"

        with mock.patch("tidal_dl.paths.SETTINGS") as settings:
            settings.saveAsFlac = False
            self.assertEqual(__getExtension__(stream), ".m4a")

    def test_save_as_flac_setting_uses_flac_extension_for_dash_flac(self):
        stream = StreamUrl()
        stream.url = "https://example.invalid/init.mp4"
        stream.codec = "flac"
        stream.manifestMimeType = "application/dash+xml"
        stream.container = "mp4"

        with mock.patch("tidal_dl.paths.SETTINGS") as settings:
            settings.saveAsFlac = True
            self.assertEqual(__getExtension__(stream), ".flac")

    def test_native_flac_url_uses_flac_extension(self):
        stream = StreamUrl()
        stream.url = "https://example.invalid/audio.flac"
        stream.codec = "flac"

        self.assertEqual(__getExtension__(stream), ".flac")

    def test_atmos_eac3_dash_uses_m4a_extension(self):
        stream = StreamUrl()
        stream.url = "https://example.invalid/init.mp4"
        stream.codec = "ec-3"
        stream.manifestMimeType = "application/dash+xml"
        stream.container = "mp4"

        self.assertEqual(__getExtension__(stream), ".m4a")

    def test_path_summary_contains_user_visible_locations(self):
        labels = [label for label, value in PATHS.getPathSummary()]

        self.assertIn("Download path", labels)
        self.assertIn("Config folder", labels)
        self.assertIn("Settings file", labels)
        self.assertIn("Token file", labels)
        self.assertIn("Log file", labels)

    def test_config_directory_matches_settings_parent(self):
        self.assertTrue(PATHS.getConfigDirectory())

    def test_open_path_creates_folder_and_launches_file_manager(self):
        with mock.patch("tidal_dl.paths.sys.platform", "linux"):
            with mock.patch("tidal_dl.paths.os.makedirs") as makedirs:
                with mock.patch("tidal_dl.paths.subprocess.Popen") as popen:
                    opened = openPath("/tmp/tidekeeper-test-folder")

        self.assertEqual(opened, "/tmp/tidekeeper-test-folder")
        makedirs.assert_called_once_with("/tmp/tidekeeper-test-folder", exist_ok=True)
        popen.assert_called_once_with(["xdg-open", "/tmp/tidekeeper-test-folder"])

    def test_open_path_uses_platform_opener_on_macos(self):
        with mock.patch("tidal_dl.paths.sys.platform", "darwin"):
            with mock.patch("tidal_dl.paths.os.makedirs"):
                with mock.patch("tidal_dl.paths.subprocess.Popen") as popen:
                    openPath("/tmp/tidekeeper-test-folder")

        popen.assert_called_once_with(["open", "/tmp/tidekeeper-test-folder"])

    def test_open_path_uses_platform_opener_on_windows(self):
        with mock.patch("tidal_dl.paths.sys.platform", "win32"):
            with mock.patch("tidal_dl.paths.os.makedirs"):
                with mock.patch("tidal_dl.paths.os.startfile", create=True) as startfile:
                    openPath("C:/Tidekeeper")

        startfile.assert_called_once()


if __name__ == "__main__":
    unittest.main()
