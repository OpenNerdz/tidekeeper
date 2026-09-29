"""Tags, album info files, and metadata repair."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tidal_dl import download
from tidal_dl.model import Album, Artist, Track
from tidal_dl.settings import SETTINGS
from tidal_dl.tidal import TIDAL_API, TidalAPI
from tidal_dl.transfer_state import (
    audio_identity,
    is_completed,
    record_completion,
)

from fixtures import CatalogFixtures, FakeResponse, TransferFixture


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
        with mock.patch.object(download, "_writeTextFile", side_effect=PermissionError("denied")), \
                mock.patch.object(download.Printf, "err") as err:
            self.assertFalse(download.downloadAlbumInfo(self._album(1), [_track("One", 1, 1)]))
        self.assertIn("AlbumInfo.txt", err.call_args[0][0])


class MetadataRepairTests(TransferFixture, unittest.TestCase):
    def test_metadata_failure_is_repaired_on_retry_before_skip(self):
        path = str(self.root / 'track.flac')
        track = SimpleNamespace(id=1, title='Track', allowStreaming=True, streamReady=True)
        stream = SimpleNamespace(trackid=1, soundQuality='LOSSLESS', codec='flac',
                                 container='flac', encryptionKey=None,
                                 url='https://cdn.invalid/file', urls=['https://cdn.invalid/file'])
        SETTINGS.checkExist = True
        SETTINGS.showTrackInfo = SETTINGS.showProgress = SETTINGS.multiThread = False
        warnings = []
        progress = SimpleNamespace(updateStream=lambda stream: None, note_warning=warnings.append)
        # An older receipt must not make the failed replacement look complete.
        Path(path).write_bytes(b'media')
        record_completion(path, audio_identity(stream))
        SETTINGS.checkExist = False
        with mock.patch.object(download, '_resolveTrackForAtmosDownload', return_value=(track, None)), \
             mock.patch.object(download, '_getTrackStream', return_value=stream), \
             mock.patch.object(download, 'getTrackPath', return_value=path), \
             mock.patch.object(download, '_remoteSize', return_value=5), \
             mock.patch.object(download, '_httpRequest', return_value=FakeResponse(b'media')) as request, \
             mock.patch.object(TIDAL_API, 'getTrackContributors', return_value=None), \
             mock.patch.object(download, '_saveLyricsForTrack', return_value=''), \
             mock.patch.object(download, '_setMetaData', side_effect=OSError('tagging failed')) as tag:
            self.assertTrue(download.downloadTrack(track, userProgress=progress)[0])
            self.assertEqual(len(warnings), 1)
            self.assertFalse(is_completed(path, audio_identity(stream)))
            self.assertFalse(Path(path + '.part').exists(), 'Completed media should not be retained twice')

            SETTINGS.checkExist = True
            warnings.clear()
            tag.side_effect = None
            with mock.patch.object(download, 'completion_state', wraps=download.completion_state) as inspect:
                self.assertTrue(download.downloadTrack(track, userProgress=progress)[0])
                inspect.assert_called_once_with(path, audio_identity(stream))
            self.assertEqual(tag.call_count, 2)
            self.assertEqual(request.call_count, 1, 'Retry should repair tags without another CDN request')
            self.assertFalse(warnings)
            self.assertTrue(is_completed(path, audio_identity(stream)))
            self.assertFalse(Path(path + '.part').exists())
            self.assertFalse(Path(path + '.part.source.json').exists())

            self.assertTrue(download.downloadTrack(track, userProgress=progress)[0])
            self.assertEqual(tag.call_count, 2, 'Fully repaired files should be skipped')


class MetadataTagTests(CatalogFixtures, unittest.TestCase):
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
            download._setMetaData(track, album, "/tmp/track.m4a", None, "")

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
            download._setMetaData(track, album, "/tmp/track.m4a", None, "")

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
                download._setMetaData(track, album, "/tmp/track.m4a", None, "")

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
            download._setMetaData(track, album, "/tmp/track.m4a", None, "")

        fake_handle.add_tags.assert_called_once_with()
        fake_tag.save.assert_called_once_with("")


if __name__ == "__main__":
    unittest.main()
