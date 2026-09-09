import os
import tempfile
import unittest
from unittest import mock

from tidal_dl.environment import getDefaultDownloadPath, getTermuxDownloadPath, isTermux
from tidal_dl.settings import Settings


class TermuxEnvironmentTests(unittest.TestCase):
    def test_explicit_empty_environment_does_not_use_host_environment(self):
        with mock.patch.dict(os.environ, {"TERMUX_VERSION": "test"}):
            self.assertFalse(isTermux({}))
            self.assertEqual(getDefaultDownloadPath({}), "./download/")

    def test_download_override_works_outside_termux_including_docker(self):
        self.assertEqual(getDefaultDownloadPath({"TIDEKEEPER_DOWNLOAD_PATH": "/downloads"}), "/downloads")

    def test_detects_termux_from_prefix(self):
        environ = {
            "PREFIX": "/data/data/com.termux/files/usr",
            "HOME": "/data/data/com.termux/files/home",
        }

        self.assertTrue(isTermux(environ))

    def test_non_termux_uses_local_download_folder(self):
        self.assertFalse(isTermux({"HOME": "/home/user"}))
        self.assertEqual(getDefaultDownloadPath({"HOME": "/home/user"}), "./download/")

    def test_termux_download_path_uses_external_storage(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            downloads_dir = os.path.join(temp_dir, "Download")
            os.mkdir(downloads_dir)
            environ = {
                "TERMUX_VERSION": "0.119.0",
                "EXTERNAL_STORAGE": temp_dir,
            }

            self.assertEqual(
                getTermuxDownloadPath(environ),
                os.path.join(downloads_dir, "Tidekeeper"),
            )
            self.assertEqual(
                getDefaultDownloadPath(environ),
                os.path.join(downloads_dir, "Tidekeeper"),
            )

    def test_termux_download_path_falls_back_to_home(self):
        environ = {
            "TERMUX_VERSION": "0.119.0",
            "HOME": "/data/data/com.termux/files/home",
        }

        self.assertEqual(
            getTermuxDownloadPath(environ),
            "/data/data/com.termux/files/home/downloads/Tidekeeper",
        )

    def test_new_termux_profile_gets_android_download_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings()
            profile_path = os.path.join(temp_dir, "settings.json")

            with mock.patch.dict(os.environ, {
                "TERMUX_VERSION": "0.119.0",
                "HOME": "/data/data/com.termux/files/home",
            }, clear=True):
                settings.read(profile_path)

            self.assertEqual(
                settings.downloadPath,
                "/data/data/com.termux/files/home/downloads/Tidekeeper",
            )

    def test_existing_profile_keeps_user_download_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings()
            profile_path = os.path.join(temp_dir, "settings.json")
            with open(profile_path, "w", encoding="utf-8") as output:
                output.write('{"downloadPath": "/custom/path", "audioQuality": "Max", "videoQuality": "P1080"}')

            with mock.patch.dict(os.environ, {
                "TERMUX_VERSION": "0.119.0",
                "EXTERNAL_STORAGE": "/storage/emulated/0",
            }, clear=True):
                settings.read(profile_path)

            self.assertEqual(settings.downloadPath, "/custom/path")


if __name__ == "__main__":
    unittest.main()
