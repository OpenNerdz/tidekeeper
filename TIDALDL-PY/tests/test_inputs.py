"""Link parsing and text-file link lists."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import tidal_dl
from tidal_dl import download, events, inputs, runtime
from tidal_dl.enums import Type
from tidal_dl.inputs import parse_direct_inputs
from tidal_dl.tidal import TIDAL_API, TidalAPI

from fixtures import ApiFixture, CatalogFixtures, DownloadFolderApiFixture, ProfileFixture


class ParseUrlTests(unittest.TestCase):
    def test_host_match_is_case_insensitive(self):
        api = TidalAPI()
        self.assertEqual(api.parseUrl("https://TIDAL.com/browse/album/123"), (Type.Album, "123"))
        self.assertEqual(api.parseUrl("12345"), (Type.Null, "12345"))


class LinkListTests(ProfileFixture, unittest.TestCase):
    def test_batch_supports_comments_bom_whitespace_and_nested_relative_files(self):
        outer = self.root / 'outer list.txt'
        inner = self.root / 'inner list.txt'
        outer.write_text('\ufeff  # comment\ninner list.txt\n3, 4\n', encoding='utf-8')
        inner.write_text('1\t2\nouter list.txt\n1', encoding='utf-8')
        self.assertEqual(parse_direct_inputs(str(outer)), ['1', '2', '3', '4'])
        self.assertEqual(parse_direct_inputs('# header\n1\n2'), ['1', '2'])

    def test_batch_symlink_cycle_is_read_once(self):
        path = self.root / 'list.txt'
        alias = self.root / 'alias.txt'
        try:
            alias.symlink_to(path)
        except OSError:
            self.skipTest('Creating symlinks is not permitted on this platform')
        path.write_text('alias.txt\n1\n')
        self.assertEqual(parse_direct_inputs(str(path)), ['1'])

    def test_deep_batches_do_not_use_python_recursion(self):
        for index in range(1100):
            (self.root / f'{index}.txt').write_text(f'{index + 1}.txt' if index < 1099 else '123')
        self.assertEqual(parse_direct_inputs(str(self.root / '0.txt')), ['123'])

    def test_binary_list_reports_read_error(self):
        path = self.root / 'binary.txt'
        path.write_bytes(b'\xff\xff')
        with self.assertRaisesRegex(ValueError, 'Unable to read URL list'):
            parse_direct_inputs(str(path))

    def test_cli_continues_batch_after_lookup_failure(self):
        with mock.patch.object(TIDAL_API, 'getByString', side_effect=[ValueError('missing'), (Type.Track, 'track')]), \
             mock.patch.object(events, 'start_type', return_value=True) as start_type:
            self.assertFalse(events.start('1 2'))
            start_type.assert_called_once_with(Type.Track, 'track', False, progress=None)

    def test_cli_nested_batch_keeps_following_items(self):
        path = self.root / 'nested.txt'
        path.write_text('1\n')
        with mock.patch.object(TIDAL_API, 'getByString', side_effect=lambda value: (Type.Track, value)), \
             mock.patch.object(events, 'start_type', return_value=True) as start_type:
            self.assertTrue(events.start(f'{path}\n2'))
        self.assertEqual([call.args[1] for call in start_type.call_args_list], ['1', '2'])

    def test_legacy_download_notice_is_shown_once_before_downloads(self):
        previous = events._legacyNoticeShown
        self.addCleanup(setattr, events, '_legacyNoticeShown', previous)
        events._legacyNoticeShown = False
        with mock.patch.object(events, 'legacyDownloadNotice', return_value='Move old downloads'), \
                mock.patch.object(events.Printf, 'info') as info, \
                mock.patch.object(events, 'start_track', return_value=True):
            self.assertTrue(events.start_type(Type.Track, object()))
            self.assertTrue(events.start_type(Type.Track, object()))
        info.assert_called_once_with('Move old downloads')


class InputLimitTests(ApiFixture, unittest.TestCase):
    def test_catalog_url_requires_exact_host_and_valid_identifier(self):
        for url in ('https://example.com/browse/track/123', 'https://tidal.com/browse/track/two-words'):
            self.assertEqual(self.api.parseUrl(url), (Type.Null, url))
            with mock.patch.object(self.api, 'getTypeData') as get, self.assertRaises(ValueError):
                self.api.getByString(url)
            get.assert_not_called()
        self.assertEqual(self.api.parseUrl('https://listen.TIDAL.com/track/123'), (Type.Track, '123'))

    def test_nested_list_size_is_bounded(self):
        (self.root / 'items.txt').write_text('123456789', encoding='utf-8')
        with mock.patch.object(inputs, 'MAX_LIST_BYTES', len(str(self.root / 'items.txt')) + 3), \
                self.assertRaises(ValueError):
            inputs.parse_direct_inputs(str(self.root / 'items.txt'))

    def test_list_entry_count_is_bounded(self):
        with mock.patch.object(inputs, 'MAX_INPUTS', 2), self.assertRaises(ValueError):
            inputs.parse_direct_inputs('1\n2\n3')


class SchemelessLinkTests(DownloadFolderApiFixture, unittest.TestCase):
    def test_schemeless_links_keep_strict_host_and_id_validation(self):
        for link, expected in (
            ('tidal.com/browse/album/123', (Type.Album, '123')),
            ('listen.tidal.com/track/1', (Type.Track, '1')),
            ('WWW.TIDAL.COM/browse/video/42', (Type.Video, '42')),
            ('tidal.com:443/browse/playlist/abc-123?source=share', (Type.Playlist, 'abc-123')),
        ):
            with self.subTest(link=link):
                self.assertEqual(self.api.parseUrl(link), expected)
        for link in ('tidal.com.example/track/1', 'tidal.com@other.example/track/1',
                     'not-tidal.com/track/1', 'tidal.com/track/not-a-number',
                     'tidal.com:81/track/1', '//other.example/track/1'):
            with self.subTest(link=link):
                self.assertEqual(self.api.parseUrl(link)[0], Type.Null)

    def test_cli_link_and_batch_resolve_schemeless_catalog_links(self):
        batch = self.root / 'links.txt'
        batch.write_text('tidal.com/browse/album/123\nlisten.tidal.com/track/1\n')
        for argument, expected in (
            ('tidal.com/browse/album/123', [('123', Type.Album)]),
            (str(batch), [('123', Type.Album), ('1', Type.Track)]),
        ):
            with self.subTest(argument=argument), \
                    mock.patch('sys.argv', ['tidekeeper', '--link', argument]), \
                    mock.patch.object(tidal_dl, 'loginByConfig', return_value=True), \
                    mock.patch.object(events, 'TIDAL_API', self.api), \
                    mock.patch.object(self.api, 'getTypeData', return_value=object()) as lookup, \
                    mock.patch.object(events, 'start_type', return_value=True), \
                    runtime.job_context(output=lambda text: None):
                self.assertEqual(tidal_dl.mainCommand(), 0)
                self.assertEqual([call.args for call in lookup.call_args_list], expected)


class LinkParsingTests(CatalogFixtures, unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
