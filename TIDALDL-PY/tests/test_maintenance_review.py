"""Regression coverage for local data, batch processing, and cleanup."""
import copy
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from tidal_dl import diagnostics, download, events
from tidal_dl.enums import Type
from tidal_dl.gui_app.backend import TidekeeperBackend
from tidal_dl.inputs import parse_direct_inputs
from tidal_dl.runtime import DownloadCancelled
from tidal_dl.settings import SETTINGS, TOKEN, Settings, TokenSettings
from tidal_dl.tidal import TIDAL_API, TidalAPI


class MaintenanceReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for singleton in (SETTINGS, TOKEN):
            original = copy.deepcopy(singleton.__dict__)
            self.addCleanup(self.restore, singleton, original)

    @staticmethod
    def restore(singleton, values):
        singleton.__dict__.clear()
        singleton.__dict__.update(values)

    def test_doctor_preserves_existing_file_and_leaves_no_probe(self):
        sentinel = self.root / '.tidekeeper-write-test'
        sentinel.write_text('keep this file')
        SETTINGS.downloadPath = str(self.root)
        self.assertEqual(diagnostics.__checkDownloadPath__()[0], 'OK')
        self.assertEqual(sentinel.read_text(), 'keep this file')
        self.assertEqual(list(self.root.iterdir()), [sentinel])

    def test_token_reread_drops_previous_credentials(self):
        token = TokenSettings()
        path = self.root / 'token.json'
        path.write_text(json.dumps({'accessToken': 'old-token', 'userid': 7}))
        token.read(str(path))
        self.assertEqual(token.accessToken, 'old-token')
        path.write_text('{broken')
        token.read(str(path))
        self.assertIsNone(token.accessToken)
        self.assertIsNone(token.userid)
        path.unlink()
        token.accessToken = 'stale'
        token.read(str(path))
        self.assertIsNone(token.accessToken)

    def test_numeric_tokens_are_rejected_but_numeric_user_ids_work(self):
        path = self.root / 'token.json'
        path.write_text(json.dumps({'accessToken': 123, 'refreshToken': True, 'countryCode': 4, 'userid': 7}))
        token = TokenSettings()
        token.read(str(path))
        self.assertEqual(token.userid, 7)
        self.assertIsNone(token.accessToken)
        self.assertIsNone(token.refreshToken)
        self.assertIsNone(token.countryCode)

    def test_token_file_preserves_originating_client(self):
        path = self.root / 'token.json'
        token = TokenSettings()
        token.read(str(path))
        token.userid = 7
        token.clientId = 'client-one'
        token.accessToken = 'saved-token'
        token.save()

        loaded = TokenSettings()
        loaded.read(str(path))

        self.assertEqual(loaded.clientId, 'client-one')
        self.assertEqual(loaded.accessToken, 'saved-token')

    def test_client_change_clears_legacy_or_mismatched_session(self):
        api = TidalAPI()
        api.apiKey = {'clientId': 'current-client'}
        TOKEN.userid = 7
        TOKEN.countryCode = 'US'
        TOKEN.clientId = None
        TOKEN.accessToken = 'legacy-token'
        TOKEN.refreshToken = 'legacy-refresh'

        revoked = mock.Mock(status_code=204, close=mock.Mock())
        with mock.patch.object(TOKEN, 'save') as save, mock.patch.object(api.session, 'post', return_value=revoked):
            self.assertTrue(api.clearSavedSessionIfClientChanged())

        self.assertIsNone(TOKEN.accessToken)
        self.assertIsNone(TOKEN.refreshToken)
        self.assertIsNone(TOKEN.clientId)
        save.assert_called_once_with()

        TOKEN.clientId = 'current-client'
        TOKEN.accessToken = 'current-token'
        with mock.patch.object(TOKEN, 'save') as save:
            self.assertFalse(api.clearSavedSessionIfClientChanged())
        self.assertEqual(TOKEN.accessToken, 'current-token')
        save.assert_not_called()

    def test_settings_reread_uses_defaults_after_corruption(self):
        settings = Settings()
        path = self.root / 'settings.json'
        path.write_text('{"multiThread": true, "trackFileFormat": "old"}')
        settings.read(str(path))
        self.assertTrue(settings.multiThread)
        path.write_text('invalid')
        settings.read(str(path))
        self.assertFalse(settings.multiThread)
        self.assertEqual(settings.trackFileFormat, Settings.trackFileFormat)

    def test_profiles_with_invalid_utf8_clear_stale_values(self):
        for profile, field, stale in ((Settings(), 'multiThread', True),
                                      (TokenSettings(), 'accessToken', 'old-token')):
            with self.subTest(profile=type(profile).__name__):
                path = self.root / 'profile.json'
                path.write_bytes(b'\xff\xfe')
                setattr(profile, field, stale)
                with self.assertLogs(level='WARNING'):
                    profile.read(str(path))
                self.assertFalse(getattr(profile, field))
                self.assertEqual(path.read_bytes(), b'\xff\xfe')

    def test_utf8_bom_profiles_preserve_saved_values(self):
        path = self.root / 'settings.json'
        path.write_text(json.dumps({'downloadPath': '/Music/Bj\u00f6rk'}, ensure_ascii=False), encoding='utf-8-sig')
        settings = Settings()
        settings.read(str(path))
        self.assertEqual(settings.downloadPath, '/Music/Bj\u00f6rk')
        token_path = self.root / 'token.json'
        token_path.write_text(json.dumps({'userid': 7, 'accessToken': 'saved-token'}), encoding='utf-8-sig')
        token = TokenSettings()
        token.read(str(token_path))
        self.assertEqual(token.userid, 7)
        self.assertEqual(token.accessToken, 'saved-token')

    def test_gui_manual_login_does_not_reuse_old_refresh_token(self):
        TOKEN.refreshToken = 'previous-session'
        key = SimpleNamespace(userId=7, countryCode='US', accessToken='new', refreshToken='previous-session')
        with mock.patch.object(TIDAL_API, 'key', key), mock.patch.object(TIDAL_API, 'loginByAccessToken'), \
             mock.patch.object(TOKEN, 'save'):
            TidekeeperBackend().login_by_access_token('new')
            self.assertIsNone(TOKEN.refreshToken)
            self.assertIsNone(key.refreshToken)

    def test_cli_manual_login_does_not_reuse_old_refresh_token(self):
        TOKEN.refreshToken = 'previous-session'
        key = SimpleNamespace(userId=7, countryCode='US', accessToken='new', refreshToken='previous-session')
        with mock.patch.object(TIDAL_API, 'key', key), mock.patch.object(TIDAL_API, 'loginByAccessToken'), \
             mock.patch.object(events.Printf, 'enterSecret', side_effect=['new', '0']), mock.patch.object(TOKEN, 'save'):
            events.loginByAccessToken()
            self.assertIsNone(TOKEN.refreshToken)
            self.assertIsNone(key.refreshToken)

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

    def test_catalog_full_last_page_does_not_request_an_extra_page(self):
        api = TidalAPI()
        self.addCleanup(api.session.close)
        rows = list(range(50))
        with mock.patch.object(api, '__get__', return_value={'totalNumberOfItems': 50, 'items': rows}) as get:
            self.assertEqual(api.__getItems__('albums'), rows)
            get.assert_called_once()

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

    def test_cancelled_assembly_preserves_output_and_removes_temporary_file(self):
        source = self.root / 'part'
        output = self.root / 'result'
        source.write_bytes(b'new data')
        output.write_bytes(b'previous data')
        with mock.patch.object(download, 'check_cancelled', side_effect=DownloadCancelled):
            with self.assertRaises(DownloadCancelled):
                download.__concatenateFiles__([str(source)], str(output))
        self.assertEqual(output.read_bytes(), b'previous data')
        self.assertFalse(Path(f'{output}.tmp.{os.getpid()}').exists())
        self.assertEqual(source.read_bytes(), b'new data')

    def test_cancelled_flac_export_cleans_up_ffmpeg_output(self):
        SETTINGS.saveAsFlac = True
        source = self.root / 'track.m4a'
        source.write_bytes(b'media')
        temporary = self.root / f'track.flac.tmp.{os.getpid()}.flac'

        def cancel(*args, **kwargs):
            temporary.write_bytes(b'incomplete')
            raise DownloadCancelled()

        stream = SimpleNamespace(codec='flac', container='mp4', manifestMimeType='')
        with mock.patch.object(download.shutil, 'which', return_value='ffmpeg'), \
             mock.patch.object(download, 'run_process', side_effect=cancel), self.assertRaises(DownloadCancelled):
            download.__exportFlacFromContainer__(str(source), stream)
        self.assertFalse(temporary.exists())
        self.assertEqual(source.read_bytes(), b'media')
