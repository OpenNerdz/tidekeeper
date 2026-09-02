import unittest
from types import SimpleNamespace
from unittest import mock

from tidal_dl.model import StreamUrl
from tidal_dl.paths import __getExtension__, PATHS, getAlbumPath, getTrackPath, openPath


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

    def _album(self):
        artist = SimpleNamespace(name="Artist", id=123)
        return SimpleNamespace(
            id=123,
            artists=[artist],
            artist=artist,
            title="Album",
            releaseDate="2026:01:02",
            audioQuality="HIGH",
            audioModes=[],
            explicit=False,
            duration=3723,
            numberOfTracks=1,
            numberOfVideos=0,
            numberOfVolumes=1,
            type="ALBUM",
            cover=None,
        )

    def test_duration_and_release_date_tokens_strip_windows_illegal_chars(self):
        """{Duration} is H:MM:SS; colons are illegal on Windows path components."""
        album = self._album()
        illegal = set('<>:"/\\|?*')
        from tidal_dl import paths
        with mock.patch.object(paths.SETTINGS, "albumFolderFormat", "{Duration}_{ReleaseDate}_{AlbumTitle}"), \
             mock.patch.object(paths.SETTINGS, "downloadPath", "/tmp/tidekeeper"):
            path = getAlbumPath(album)

        self.assertTrue(path.startswith("/tmp/tidekeeper/"))
        leaf = path[len("/tmp/tidekeeper/"):]
        self.assertEqual(leaf, "1-02-03_2026-01-02_Album")
        self.assertFalse(illegal.intersection(leaf))

        track = SimpleNamespace(
            id=456,
            artists=[album.artist],
            artist=album.artist,
            album=album,
            title="Track",
            version=None,
            explicit=False,
            trackNumber=1,
            trackNumberOnPlaylist=1,
            volumeNumber=1,
            audioQuality="HIGH",
            duration=3723,
        )
        stream = StreamUrl()
        stream.url = "https://example.invalid/audio.m4a"
        stream.codec = "aac"
        stream.container = "mp4"
        stream.manifestMimeType = ""
        stream.soundQuality = "LOSSLESS"
        from tidal_dl import paths
        with mock.patch.object(paths.SETTINGS, "albumFolderFormat", "{AlbumTitle}"), \
             mock.patch.object(paths.SETTINGS, "trackFileFormat", "{TrackNumber} {Duration} {TrackTitle}"), \
             mock.patch.object(paths.SETTINGS, "downloadPath", "/tmp/tidekeeper"), \
             mock.patch.object(paths.SETTINGS, "saveAsFlac", False):
            track_path = getTrackPath(track, stream, album)

        self.assertIn("01 1-02-03 Track.m4a", track_path)
        name = track_path.rsplit("/", 1)[-1]
        self.assertFalse(illegal.intersection(name.replace(".m4a", "")))


if __name__ == "__main__":
    unittest.main()
