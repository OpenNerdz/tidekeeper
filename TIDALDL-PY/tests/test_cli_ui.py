import io
import logging
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import tidal_dl
from tidal_dl import apiKey, events, paths, printf
from tidal_dl.enums import AudioQuality, VideoQuality
from tidal_dl.model import Track
from tidal_dl.paths import PATHS
from tidal_dl.printf import Printf
from tidal_dl.settings import SETTINGS, TOKEN

from fixtures import ApiFixture, CatalogFixtures, TransferFixture


class CliUiTests(unittest.TestCase):
    def setUp(self):
        PATHS.homePathOverride = None
        self.addCleanup(setattr, PATHS, "homePathOverride", None)

    def _isolateConfigHome(self):
        """Point config/token lookups at a throwaway directory.

        `main()` reads and can save the profile and token files, so tests must
        never touch (or depend on) the real config of whoever runs the suite.
        """
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        root_logger = logging.getLogger()
        original_handlers = list(root_logger.handlers)
        original_level = root_logger.level

        def restore_logging():
            for handler in list(root_logger.handlers):
                if handler not in original_handlers:
                    root_logger.removeHandler(handler)
                    handler.close()
            root_logger.setLevel(original_level)

        # Close log files before removing the temporary config directory.
        self.addCleanup(restore_logging)
        PATHS.homePathOverride = tmpdir.name
        self._restoreGlobalSettings()
        return tmpdir.name

    def _restoreGlobalSettings(self):
        for model in (SETTINGS, TOKEN):
            snapshot = dict(vars(model))
            self.addCleanup(self._applySnapshot, model, snapshot)

    @staticmethod
    def _applySnapshot(model, snapshot):
        vars(model).clear()
        vars(model).update(snapshot)

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
        output = io.StringIO()

        with mock.patch.object(printf, "isTermux", return_value=True):
            with redirect_stdout(output):
                Printf.apikeys(apiKey.getItems())

        text = output.getvalue()
        self.assertIn("TIDAL clients", text)
        self.assertIn("1 - Fire TV (legacy)", text)
        self.assertIn("4 - Tidal TV", text)
        self.assertIn("5 - Tidal HiRes", text)
        self.assertNotIn("+", text)

    def test_wide_api_key_picker_preserves_sparse_ids(self):
        with mock.patch.object(Printf, '_isCompact', return_value=False), \
             mock.patch.object(Printf, '_gettable') as table:
            Printf.apikeys(apiKey.getItems())
        self.assertEqual([row[0] for row in table.call_args.args[1]], [1, 4, 5])

    def test_quality_menu_uses_current_qualities_and_all_resolutions(self):
        from tidal_dl.enums import AudioQuality, VideoQuality
        self._restoreGlobalSettings()
        with mock.patch.object(Printf, 'settings'), mock.patch.object(SETTINGS, 'save'), \
             mock.patch.object(Printf, 'enter', return_value=''), \
             mock.patch.object(Printf, 'enterLimit', side_effect=['5', '240']) as enter:
            events.changeQualitySettings()
        audio, video = enter.call_args_list
        self.assertIn("'5'-Atmos", audio.args[0])
        self.assertNotIn('Master', audio.args[0])
        self.assertNotIn('3', audio.args[2])
        self.assertIn('240', video.args[0])
        self.assertIn('240', video.args[2])
        self.assertEqual(SETTINGS.audioQuality, AudioQuality.Atmos)
        self.assertEqual(SETTINGS.videoQuality, VideoQuality.P240)

    def test_quality_menu_keeps_selected_quality_ahead_of_fallbacks(self):
        from tidal_dl.enums import AudioQuality
        self._restoreGlobalSettings()
        with mock.patch.object(Printf, 'settings'), mock.patch.object(SETTINGS, 'save'), \
             mock.patch.object(Printf, 'enter', return_value='HiFi,High,Normal'), \
             mock.patch.object(Printf, 'enterLimit', side_effect=['4', '240']):
            events.changeQualitySettings()

        self.assertEqual(SETTINGS.audioQuality, AudioQuality.Max)
        self.assertEqual(SETTINGS.getDownloadAudioQualityPriority(), [
            AudioQuality.Max, AudioQuality.HiFi, AudioQuality.High, AudioQuality.Normal,
        ])

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

    def test_doctor_command_returns_nonzero_when_checks_fail(self):
        with mock.patch("sys.argv", ["tidekeeper", "--doctor"]), \
             mock.patch.object(tidal_dl, "runDoctor", return_value=False):
            code = tidal_dl.mainCommand()

        self.assertEqual(code, 1)

    def test_gui_command_propagates_startup_failure(self):
        with mock.patch("sys.argv", ["tidekeeper", "--gui"]), \
             mock.patch.object(tidal_dl.aigpy.path, "mkdirs", return_value=True), \
             mock.patch.object(tidal_dl, "startGui", return_value=1):
            code = tidal_dl.mainCommand()

        self.assertEqual(code, 1)

    def test_download_folder_error_shows_the_expanded_path(self):
        self._restoreGlobalSettings()
        SETTINGS.downloadPath = '~/Music'
        with tempfile.TemporaryDirectory() as home, mock.patch.dict('os.environ', {'HOME': home}), \
                mock.patch.object(tidal_dl.aigpy.path, 'mkdirs', return_value=False), \
                mock.patch.object(Printf, 'err') as error:
            self.assertEqual(tidal_dl.mainCommand(opts=[]), 1)
        self.assertIn(str(Path(home) / 'Music'), error.call_args.args[0])
        self.assertNotIn('~/Music', error.call_args.args[0])

    def test_paths_flag_prints_paths_without_login(self):
        with mock.patch("sys.argv", ["tidekeeper", "--paths"]):
            with mock.patch.object(Printf, "paths") as paths:
                tidal_dl.mainCommand()

        paths.assert_called_once_with()

    def test_migrate_downloads_command_runs_without_login(self):
        with mock.patch('tidal_dl.paths.migrateLegacyDownloads', return_value='Moved old downloads') as migrate, \
                mock.patch.object(Printf, 'success') as success:
            self.assertEqual(tidal_dl.mainCommand(opts=[('--migrate-downloads', '/old/~/Music')]), 0)
        migrate.assert_called_once_with('/old/~/Music')
        success.assert_called_once_with('Moved old downloads')

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
        assert(PATHS._getHomePath() == PATHS._getDefaultHomePath())

    def test_config_path_override_overrides_paths(self):
        with mock.patch("sys.argv", ["tidekeeper", "-c", "/home/user/tidekeeper/config"]):
            with mock.patch("tidal_dl.os.path.isdir") as mock_isdir:
                mock_isdir.return_value = True
                tidal_dl.preMainCommand()
        assert(PATHS._getHomePath() == "/home/user/tidekeeper/config")

    def test_config_path_requires_existing_directory(self):
        with mock.patch("sys.argv", ["tidekeeper", "-c", "/magic/config"]):
            with self.assertRaises(ValueError):
                tidal_dl.preMainCommand()

    def test_main_reports_invalid_config_path_without_traceback(self):
        with mock.patch("sys.argv", ["tidekeeper", "-c", "/missing/config"]), \
             mock.patch.object(Printf, "err") as error:
            code = tidal_dl.main()

        self.assertEqual(code, 1)
        self.assertIn("existing directory", error.call_args.args[0])

    def test_sys_argvs_prevent_entering_while_loop(self):
        self._isolateConfigHome()
        with mock.patch("sys.argv", ["tidekeeper", "--paths"]):
            with mock.patch("tidal_dl.Printf.choices") as mock_choices:
                mock_choices.side_effect = KeyboardInterrupt
                tidal_dl.main()
        mock_choices.assert_not_called()

    def test_sys_argvs_enable_entering_while_loop(self):
        config_home = self._isolateConfigHome()
        with mock.patch("sys.argv", ["tidekeeper", "-c", config_home]), \
             mock.patch("tidal_dl.loginByWeb"), \
             mock.patch("tidal_dl.Printf.choices", side_effect=KeyboardInterrupt) as choices:
            self.assertEqual(tidal_dl.main(), 130)
        choices.assert_called()
        self.assertEqual(PATHS._getHomePath(), config_home)
        self.assertTrue(Path(PATHS.getLogPath()).is_file())


class CliOutputTests(unittest.TestCase):
    def test_track_summary_accepts_missing_album_metadata(self):
        track = Track()
        track.id = 123
        track.title = 'Track without album metadata'
        track.album = None
        output = io.StringIO()
        with redirect_stdout(output):
            Printf.track(track)
        self.assertIn(track.title, output.getvalue())

    def test_collection_summaries_accept_missing_titles(self):
        album = SimpleNamespace(id=1, title=None, numberOfTracks=2, numberOfVideos=0, releaseDate=None,
                                version=None, explicit=False, audioQuality=None, audioModes=None)
        playlist = SimpleNamespace(uuid='abc', title=None, numberOfTracks=1, numberOfVideos=0)
        artist = SimpleNamespace(id=2, name=None, type=None)
        with redirect_stdout(io.StringIO()), mock.patch.object(printf.TIDAL_API, 'getFlag', return_value=''):
            Printf.album(album)
            Printf.playlist(playlist)
            Printf.artist(artist, 0)

    def test_every_language_provides_every_english_label(self):
        from tidal_dl.lang.english import LangEnglish
        from tidal_dl.lang.language import LANG

        keys = [name for name in vars(LangEnglish) if name.isupper()]
        original = SETTINGS.language
        self.addCleanup(LANG.setLang, original)
        for index, name in LANG.choices():
            with self.subTest(language=name):
                LANG.setLang(index)
                for key in keys:
                    self.assertTrue(getattr(LANG.select, key))


class PrintfLockTests(unittest.TestCase):
    def test_failed_console_write_releases_the_lock(self):
        failure = UnicodeEncodeError("ascii", "x", 0, 1, "unencodable")
        for method in (printf.Printf.err, printf.Printf.info, printf.Printf.success):
            with self.subTest(method=method.__name__):
                with mock.patch.object(printf, "print", side_effect=failure):
                    with self.assertRaises(UnicodeEncodeError):
                        method("message")
                self.assertFalse(printf.print_mutex.locked())


class ConfigOverrideTests(TransferFixture, unittest.TestCase):
    def test_config_override_equals_and_space_forms(self):
        old = PATHS.homePathOverride
        self.addCleanup(setattr, PATHS, 'homePathOverride', old)
        for args in [['--configPathOverride=' + str(self.root)], ['--configPathOverride', str(self.root)],
                     ['-c', str(self.root)], ['-c' + str(self.root)]]:
            with self.subTest(args=args), mock.patch.object(sys, 'argv', ['tidekeeper', *args, '--help']):
                tidal_dl.preMainCommand()
                self.assertEqual(PATHS.homePathOverride, str(self.root))


class CommandOptionTests(ApiFixture, unittest.TestCase):
    def test_help_and_version_do_not_read_or_write_a_profile(self):
        for flag in ('--help', '--version'):
            with self.subTest(flag=flag), mock.patch('sys.argv', ['tidekeeper', flag]), \
                    mock.patch.object(SETTINGS, 'read') as read, \
                    mock.patch.object(tidal_dl, 'configure_logging') as configure, \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(tidal_dl.main(), 0)
            read.assert_not_called()
            configure.assert_not_called()

    def test_invalid_cli_options_leave_settings_unchanged(self):
        old = dict(SETTINGS.__dict__)
        for flags in (['-o', 'different', '-q', 'typo'], ['--quality-priority', 'High,typo'],
                      ['-r', '999'], ['--quality-priority', ''], ['unrecognized'], ['--output', '']):
            with self.subTest(flags=flags), mock.patch('sys.argv', ['tidekeeper', *flags]), \
                    mock.patch.object(SETTINGS, 'save') as save, mock.patch.object(Printf, 'err'):
                self.assertEqual(tidal_dl.mainCommand(), 1)
                save.assert_not_called()
            self.assertEqual(SETTINGS.__dict__, old)

    def test_valid_cli_options_save_once(self):
        with mock.patch('sys.argv', ['tidekeeper', '-q', 'HiFi', '-r', '1080p', '--paths']), \
                mock.patch.object(SETTINGS, 'save') as save, mock.patch.object(Printf, 'paths'):
            self.assertEqual(tidal_dl.mainCommand(), 0)
        self.assertEqual(SETTINGS.audioQuality, AudioQuality.HiFi)
        self.assertEqual(SETTINGS.videoQuality, VideoQuality.P1080)
        save.assert_called_once()

    def test_cli_write_failure_rolls_back_runtime_settings(self):
        old = dict(SETTINGS.__dict__)
        with mock.patch('sys.argv', ['tidekeeper', '-q', 'Normal']), \
                mock.patch.object(SETTINGS, 'save', side_effect=OSError('Read-only folder')), \
                mock.patch.object(Printf, 'err'):
            self.assertEqual(tidal_dl.mainCommand(), 1)
        self.assertEqual(SETTINGS.__dict__, old)

    def test_option_values_are_not_mistaken_for_config_flags(self):
        with mock.patch('sys.argv', ['tidekeeper', '-o', '-collection', '--paths']), \
                mock.patch.object(paths.PATHS, 'homePathOverride', None):
            tidal_dl.preMainCommand()
            self.assertIsNone(paths.PATHS.homePathOverride)


class CommandBehaviorTests(CatalogFixtures, unittest.TestCase):
    def test_link_command_aborts_when_login_fails(self):
        old_argv = sys.argv
        sys.argv = ["tidekeeper", "--link", "123456"]
        try:
            with mock.patch.object(tidal_dl.aigpy.path, "mkdirs", return_value=True), \
                 mock.patch.object(tidal_dl, "loginByConfig", return_value=False), \
                 mock.patch.object(tidal_dl, "loginByWeb", return_value=False), \
                 mock.patch.object(tidal_dl, "start") as start:
                tidal_dl.mainCommand()
        finally:
            sys.argv = old_argv

        start.assert_not_called()

    def test_quality_priority_command_sets_fallback_order(self):
        old_argv = sys.argv
        old_quality = tidal_dl.SETTINGS.audioQuality
        old_priority = tidal_dl.SETTINGS.audioQualityPriority
        sys.argv = ["tidekeeper", "--quality-priority", "Atmos,High,HiFi,Normal"]
        try:
            with mock.patch.object(tidal_dl.aigpy.path, "mkdirs", return_value=True), \
                 mock.patch.object(tidal_dl.SETTINGS, "save") as save:
                tidal_dl.mainCommand()

            self.assertEqual(tidal_dl.SETTINGS.audioQuality, AudioQuality.Atmos)
            self.assertEqual(tidal_dl.SETTINGS.audioQualityPriority, [
                AudioQuality.Atmos,
                AudioQuality.High,
                AudioQuality.HiFi,
                AudioQuality.Normal,
            ])
            save.assert_called()
        finally:
            sys.argv = old_argv
            tidal_dl.SETTINGS.audioQuality = old_quality
            tidal_dl.SETTINGS.audioQualityPriority = old_priority

    def test_quality_command_clears_fallback_order(self):
        old_argv = sys.argv
        old_quality = tidal_dl.SETTINGS.audioQuality
        old_priority = tidal_dl.SETTINGS.audioQualityPriority
        sys.argv = ["tidekeeper", "--quality", "High"]
        try:
            tidal_dl.SETTINGS.audioQualityPriority = [AudioQuality.Atmos, AudioQuality.High]
            with mock.patch.object(tidal_dl.aigpy.path, "mkdirs", return_value=True), \
                 mock.patch.object(tidal_dl.SETTINGS, "save"):
                tidal_dl.mainCommand()

            self.assertEqual(tidal_dl.SETTINGS.audioQuality, AudioQuality.High)
            self.assertEqual(tidal_dl.SETTINGS.audioQualityPriority, [])
        finally:
            sys.argv = old_argv
            tidal_dl.SETTINGS.audioQuality = old_quality
            tidal_dl.SETTINGS.audioQualityPriority = old_priority

if __name__ == "__main__":
    unittest.main()
