import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tidal_dl import paths
from tidal_dl.enums import AudioQuality
from tidal_dl.model import Album, Artist, StreamUrl, Track, Video
from tidal_dl.paths import PATHS, _getExtension, getAlbumPath, getTrackPath, getVideoPath, openPath
from tidal_dl.settings import SETTINGS
from tidal_dl.transfer_state import prepare_transfer, record_completion

from fixtures import ApiFixture, CatalogFixtures


class PathTests(unittest.TestCase):
    def test_portable_component_sanitizer_blocks_controls_devices_and_traversal(self):
        from tidal_dl.paths import _fixPath, _safeTemplatePath

        self.assertNotIn('\0', _fixPath('bad\0name'))
        self.assertEqual(_fixPath('CON'), '_CON')
        self.assertEqual(_fixPath('name. '), 'name')
        self.assertEqual(_safeTemplatePath('../outside/track'), 'outside/track')

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
            self.assertEqual(_getExtension(stream), ".m4a")

    def test_save_as_flac_setting_uses_flac_extension_for_dash_flac(self):
        stream = StreamUrl()
        stream.url = "https://example.invalid/init.mp4"
        stream.codec = "flac"
        stream.manifestMimeType = "application/dash+xml"
        stream.container = "mp4"

        with mock.patch("tidal_dl.paths.SETTINGS") as settings:
            settings.saveAsFlac = True
            self.assertEqual(_getExtension(stream), ".flac")

    def test_native_flac_url_uses_flac_extension(self):
        stream = StreamUrl()
        stream.url = "https://example.invalid/audio.flac"
        stream.codec = "flac"

        self.assertEqual(_getExtension(stream), ".flac")

    def test_atmos_eac3_dash_uses_m4a_extension(self):
        stream = StreamUrl()
        stream.url = "https://example.invalid/init.mp4"
        stream.codec = "ec-3"
        stream.manifestMimeType = "application/dash+xml"
        stream.container = "mp4"

        self.assertEqual(_getExtension(stream), ".m4a")

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
        from tidal_dl.paths import getAlbumPath, _fixPath, _getDurationStr

        raw = _getDurationStr(3723)
        self.assertIn(":", raw)
        self.assertNotIn(":", _fixPath(raw))

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


class DownloadRootTests(unittest.TestCase):
    def test_home_relative_download_folder_is_expanded_for_every_output(self):
        album = Album()
        album.id, album.title, album.releaseDate = 1, 'Album', '2020-01-01'
        album.artist = Artist()
        album.artist.id, album.artist.name = 2, 'Artist'
        album.artists = [album.artist]
        video = Video()
        video.id, video.title, video.trackNumber = 3, 'Clip', 1
        stream = StreamUrl()
        stream.url, stream.soundQuality = 'https://example.invalid/a.flac', 'LOSSLESS'
        track = Track()
        track.id, track.title, track.trackNumber = 4, 'Song', 1
        with tempfile.TemporaryDirectory() as home, mock.patch.dict(os.environ, {'HOME': home}), \
                mock.patch.object(SETTINGS, 'downloadPath', '~/Music'):
            expected = os.path.join(home, 'Music')
            for path in (getAlbumPath(album), getTrackPath(track, stream), getTrackPath(track, stream, album),
                         getVideoPath(video)):
                with self.subTest(path=path):
                    self.assertTrue(path.startswith(expected), path)
                    self.assertNotIn('~', path)

    def test_literal_tilde_folder_from_older_versions_is_reported(self):
        with tempfile.TemporaryDirectory() as working, tempfile.TemporaryDirectory() as home, \
                mock.patch.dict(os.environ, {'HOME': home}), mock.patch.object(SETTINGS, 'downloadPath', '~/Music'), \
                mock.patch('os.getcwd', return_value=working):
            literal = Path(working) / '~' / 'Music'
            literal.mkdir(parents=True)
            self.assertEqual(paths.legacyDownloadFolder(), str(literal))
            notice = paths.legacyDownloadNotice()
            self.assertIn(str(literal), notice)
            self.assertIn(str(Path(home) / 'Music'), notice)

            literal.rmdir()
            literal.parent.rmdir()
            self.assertIsNone(paths.legacyDownloadFolder())

    def test_legacy_downloads_are_merged_without_overwriting_conflicts(self):
        with tempfile.TemporaryDirectory() as working, tempfile.TemporaryDirectory() as home, \
                mock.patch.dict(os.environ, {'HOME': home}), mock.patch.object(SETTINGS, 'downloadPath', '~/Music'), \
                mock.patch('os.getcwd', return_value=working):
            literal = Path(working) / '~' / 'Music'
            (literal / 'Artist').mkdir(parents=True)
            (literal / 'Artist' / 'new.flac').write_bytes(b'new')
            (literal / 'Artist' / 'existing.flac').write_bytes(b'old copy')
            destination = Path(home) / 'Music' / 'Artist'
            destination.mkdir(parents=True)
            (destination / 'existing.flac').write_bytes(b'current copy')

            result = paths.migrateLegacyDownloads()

            self.assertIn('Moved 1 earlier download file', result)
            self.assertIn('Kept 1 conflicting file', result)
            self.assertEqual((destination / 'new.flac').read_bytes(), b'new')
            self.assertEqual((destination / 'existing.flac').read_bytes(), b'current copy')
            self.assertEqual((literal / 'Artist' / 'existing.flac').read_bytes(), b'old copy')

    def test_explicit_legacy_folder_migrates_from_an_old_working_directory(self):
        with tempfile.TemporaryDirectory() as old_working, tempfile.TemporaryDirectory() as home, \
                mock.patch.dict(os.environ, {'HOME': home}), mock.patch.object(SETTINGS, 'downloadPath', '~/Music'):
            literal = Path(old_working) / '~' / 'Music'
            literal.mkdir(parents=True)
            (literal / 'song.flac').write_bytes(b'audio')
            result = paths.migrateLegacyDownloads(str(literal))
            self.assertIn('Moved 1 earlier download file', result)
            self.assertEqual((Path(home) / 'Music' / 'song.flac').read_bytes(), b'audio')
            self.assertFalse(literal.exists())


class PathSafetyTests(ApiFixture, unittest.TestCase):
    def test_root_download_folder_is_preserved(self):
        track, stream = Track(), StreamUrl()
        SETTINGS.downloadPath = '/'
        SETTINGS.trackFileFormat = '{TrackID}'
        track.id = 123
        self.assertEqual(paths.getTrackPath(track, stream), '/123.m4a')

    def test_volume_labels_stay_in_one_directory_component(self):
        album, track, stream = Album(), Track(), StreamUrl()
        album.numberOfVolumes = 2
        album.releaseDate = '2026-01-01'
        track.volumeNumber = 'disc one / bonus'
        SETTINGS.downloadPath = str(self.root)
        SETTINGS.albumFolderFormat = 'album'
        SETTINGS.trackFileFormat = 'track'
        self.assertEqual(Path(paths.getTrackPath(track, stream, album)).parent.name, 'CDdisc one - bonus')


class PathTemplateTests(CatalogFixtures, unittest.TestCase):
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

    def test_video_artist_id_token_lists_all_ids_and_skips_missing(self):
        old_values = {
            "downloadPath": paths.SETTINGS.downloadPath,
            "videoFileFormat": paths.SETTINGS.videoFileFormat,
        }
        try:
            paths.SETTINGS.downloadPath = "/tmp/tidekeeper"
            paths.SETTINGS.videoFileFormat = "{ArtistID} - {VideoTitle}"

            video = self._video()
            video.artists = [self._artist(id=123), self._artist(name="Feat", id=456)]
            self.assertTrue(paths.getVideoPath(video).endswith("123, 456 - Video.mp4"))

            video.artists = [self._artist(id=None), self._artist(name="Feat", id=456)]
            video.artist = self._artist(id=None)
            video_path = paths.getVideoPath(video)
            self.assertNotIn("None", video_path)
            self.assertTrue(video_path.endswith("456 - Video.mp4"))
        finally:
            for key, value in old_values.items():
                setattr(paths.SETTINGS, key, value)

    def test_track_artist_tokens_keep_primary_name_and_add_new_tokens(self):
        old_values = {
            "downloadPath": paths.SETTINGS.downloadPath,
            "albumFolderFormat": paths.SETTINGS.albumFolderFormat,
            "trackFileFormat": paths.SETTINGS.trackFileFormat,
        }
        try:
            paths.SETTINGS.downloadPath = "/tmp/tidekeeper"
            paths.SETTINGS.albumFolderFormat = "{AlbumTitle}"
            track = self._track()
            track.artist = self._artist("Primary/Name", 111)
            track.artists = [self._artist("Primary/Name", 111), self._artist("Feat", 222)]

            paths.SETTINGS.trackFileFormat = "{TrackNumber} - {ArtistName} - {TrackTitle}{ExplicitFlag}"
            default_path = paths.getTrackPath(track, self._stream(), self._album())
            self.assertTrue(default_path.endswith("01 - Primary-Name - Track.m4a"))

            paths.SETTINGS.trackFileFormat = (
                "{ArtistName}|{ArtistsName}|{ArtistID}|{TrackArtistID}|{TrackArtistName}"
            )
            token_path = paths.getTrackPath(track, self._stream(), self._album())
            self.assertTrue(
                token_path.endswith("Primary-Name-Primary-Name, Feat-111, 222-111-Primary-Name.m4a")
            )
        finally:
            for key, value in old_values.items():
                setattr(paths.SETTINGS, key, value)

    def test_video_artist_tokens_keep_primary_name_and_add_new_tokens(self):
        old_values = {
            "downloadPath": paths.SETTINGS.downloadPath,
            "videoFileFormat": paths.SETTINGS.videoFileFormat,
        }
        try:
            paths.SETTINGS.downloadPath = "/tmp/tidekeeper"
            video = self._video()
            video.artist = self._artist("Primary/Name", 111)
            video.artists = [self._artist("Primary/Name", 111), self._artist("Feat", 222)]

            paths.SETTINGS.videoFileFormat = "{VideoNumber} - {ArtistName} - {VideoTitle}{ExplicitFlag}"
            default_path = paths.getVideoPath(video)
            self.assertTrue(default_path.endswith("01 - Primary-Name - Video.mp4"))

            paths.SETTINGS.videoFileFormat = (
                "{ArtistName}|{ArtistsName}|{ArtistID}|{VideoArtistID}|{VideoArtistName}"
            )
            token_path = paths.getVideoPath(video)
            self.assertTrue(
                token_path.endswith("Primary-Name-Primary-Name, Feat-111, 222-111-Primary-Name.mp4")
            )
        finally:
            for key, value in old_values.items():
                setattr(paths.SETTINGS, key, value)

    def test_track_and_video_primary_artist_tokens_omit_missing_fields(self):
        old_values = {
            "downloadPath": paths.SETTINGS.downloadPath,
            "albumFolderFormat": paths.SETTINGS.albumFolderFormat,
            "trackFileFormat": paths.SETTINGS.trackFileFormat,
            "videoFileFormat": paths.SETTINGS.videoFileFormat,
        }
        try:
            paths.SETTINGS.downloadPath = "/tmp/tidekeeper"
            paths.SETTINGS.albumFolderFormat = "{AlbumTitle}"
            paths.SETTINGS.trackFileFormat = "{TrackArtistID}/{TrackArtistName}/{TrackTitle}"
            paths.SETTINGS.videoFileFormat = "{VideoArtistID}/{VideoArtistName}/{VideoTitle}"

            track = self._track()
            track.artist = self._artist(None, None)
            track_path = paths.getTrackPath(track, self._stream(), self._album())
            self.assertNotIn("None", track_path)
            self.assertTrue(track_path.endswith("/Track.m4a"))

            video = self._video()
            video.artist = self._artist(None, None)
            video_path = paths.getVideoPath(video)
            self.assertNotIn("None", video_path)
            self.assertTrue(video_path.endswith("/Video.mp4"))
        finally:
            for key, value in old_values.items():
                setattr(paths.SETTINGS, key, value)

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

        self.assertEqual(path, "/tmp/tidekeeper/Album/0")

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

    def test_album_path_omits_missing_primary_artist_fields(self):
        album = self._album()
        album.artist = self._artist(None, None)

        with mock.patch.object(
            paths.SETTINGS,
            "albumFolderFormat",
            "{AlbumArtistID}/{AlbumArtistName}/{AlbumTitle}",
        ):
            path = paths.getAlbumPath(album)

        self.assertTrue(path.endswith("/Album"))
        self.assertNotIn("None", path)

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

    def test_album_path_handles_missing_artist_list(self):
        album = self._album()
        album.artists = None
        old_format = paths.SETTINGS.albumFolderFormat
        try:
            paths.SETTINGS.albumFolderFormat = "{ArtistName}-{ArtistID}-{AlbumTitle}"
            self.assertTrue(paths.getAlbumPath(album).endswith("--Album"))
        finally:
            paths.SETTINGS.albumFolderFormat = old_format

if __name__ == "__main__":
    unittest.main()
