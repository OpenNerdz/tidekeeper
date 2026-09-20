import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tidal_dl.enums import AudioQuality
from tidal_dl.model import Album, Artist, StreamUrl, Track, Video
from tidal_dl.paths import __getExtension__, PATHS, getAlbumPath, getTrackPath, getVideoPath, openPath
from tidal_dl.settings import SETTINGS
from tidal_dl.transfer_state import prepare_transfer, record_completion


class PathTests(unittest.TestCase):
    def test_portable_component_sanitizer_blocks_controls_devices_and_traversal(self):
        from tidal_dl.paths import __fixPath__, __safeTemplatePath__

        self.assertNotIn('\0', __fixPath__('bad\0name'))
        self.assertEqual(__fixPath__('CON'), '_CON')
        self.assertEqual(__fixPath__('name. '), 'name')
        self.assertEqual(__safeTemplatePath__('../outside/track'), 'outside/track')

    def test_long_media_names_leave_room_for_all_pipeline_files(self):
        stream = StreamUrl()
        stream.url = 'https://example.invalid/audio.mp4'
        stream.codec, stream.container = 'flac', 'mp4'
        stream.soundQuality = 'DOLBY_ATMOS'
        for title in ('A' * 400, '音楽' * 150):
            for kind in ('track', 'video'):
                with self.subTest(title=title[:4], kind=kind), tempfile.TemporaryDirectory() as directory, \
                        mock.patch.multiple(SETTINGS, downloadPath=directory, audioQuality=AudioQuality.Atmos,
                                            saveAsFlac=True, trackFileFormat='nested/{TrackTitle}',
                                            videoFileFormat='nested/{VideoTitle}'):
                    item = Track() if kind == 'track' else Video()
                    item.title = title
                    path = getTrackPath(item, stream) if kind == 'track' else getVideoPath(item)
                    Path(path).parent.mkdir(parents=True, exist_ok=True)
                    prepare_transfer(path + '.part', [stream.url])
                    Path(path).write_bytes(b'complete media')
                    record_completion(path, {'id': 'fixture'})
                    stem = os.path.splitext(path)[0]
                    pipeline_paths = [
                        path + '.part.download', path + '.part.tmp.2147483647',
                        path + '.tmp.2147483647.mp4', stem + '.lrc.tmp.2147483647',
                        stem + '.processing.2147483647.flac.tmp.2147483647.flac',
                    ]
                    for temporary in pipeline_paths:
                        self.assertLessEqual(len(os.path.basename(temporary).encode('utf-8')), 255)
                        Path(temporary).touch()
                    self.assertTrue(Path(path + '.tidekeeper.json').exists())

    def test_long_media_names_remain_distinct_and_deterministic(self):
        stream = StreamUrl()
        stream.url, stream.codec, stream.container = 'https://example.invalid/audio.flac', 'flac', 'flac'
        track = Track()
        with mock.patch.object(SETTINGS, 'trackFileFormat', '{TrackTitle}'):
            track.title = 'A' * 400 + 'one'
            first = getTrackPath(track, stream)
            self.assertEqual(getTrackPath(track, stream), first)
            track.title = 'A' * 400 + 'two'
            self.assertNotEqual(getTrackPath(track, stream), first)

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

    def test_duration_token_is_windows_safe(self):
        album = Album()
        album.id = 1
        album.title = "Album"
        album.duration = 125
        album.releaseDate = "2020-01-01"
        album.numberOfTracks = 1
        album.numberOfVideos = 0
        album.numberOfVolumes = 1
        album.audioQuality = "LOSSLESS"
        album.type = "ALBUM"
        album.artist = Artist()
        album.artist.id = 2
        album.artist.name = "Artist"
        album.artists = [album.artist]
        previous = SETTINGS.albumFolderFormat
        SETTINGS.albumFolderFormat = "{Duration}"
        try:
            with mock.patch("tidal_dl.paths.sys.platform", "win32"):
                path = getAlbumPath(album)
        finally:
            SETTINGS.albumFolderFormat = previous
        self.assertNotIn(":", os.path.basename(path))
        self.assertIn("2-05", path)

    def test_open_path_uses_platform_opener_on_windows(self):
        with mock.patch("tidal_dl.paths.sys.platform", "win32"):
            with mock.patch("tidal_dl.paths.os.makedirs"):
                with mock.patch("tidal_dl.paths.os.startfile", create=True) as startfile:
                    openPath("C:/Tidekeeper")

        startfile.assert_called_once()

    def test_duration_and_release_date_tokens_are_windows_safe(self):
        from types import SimpleNamespace
        from tidal_dl.paths import getAlbumPath, __fixPath__, __getDurationStr__

        raw = __getDurationStr__(3723)
        self.assertIn(":", raw)
        self.assertNotIn(":", __fixPath__(raw))

        album = SimpleNamespace(
            artists=[],
            artist=None,
            title="T",
            id=1,
            releaseDate="2026-09-02",
            duration=3723,
            audioQuality="LOSSLESS",
            numberOfTracks=1,
            numberOfVideos=0,
            numberOfVolumes=1,
            type="ALBUM",
        )
        with mock.patch("tidal_dl.paths.SETTINGS") as settings:
            settings.downloadPath = "/tmp"
            settings.albumFolderFormat = "{Duration}_{ReleaseDate}"
            settings.audioQuality = object()
            with mock.patch("tidal_dl.paths.TIDAL_API") as api:
                api.getArtistsID.return_value = ""
                api.getArtistsName.return_value = ""
                api.getFlag.return_value = ""
                path = getAlbumPath(album)
        name = path.rsplit("/", 1)[-1]
        for illegal in ':<>"|?*':
            self.assertNotIn(illegal, name)


if __name__ == "__main__":
    unittest.main()
