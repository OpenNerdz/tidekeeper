"""Reading, validating, and saving the settings profile."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tidal_dl import events
from tidal_dl.enums import AudioQuality, VideoQuality
from tidal_dl.settings import SETTINGS, Settings, TokenSettings, _atomicWrite

from fixtures import CatalogFixtures, ProfileFixture, TransferFixture


class LanguageSettingTests(unittest.TestCase):
    def setUp(self):
        self.saved = copy.deepcopy(SETTINGS.__dict__)
        self.addCleanup(self._restore)

    def _restore(self):
        SETTINGS.__dict__.clear()
        SETTINGS.__dict__.update(self.saved)
        events.LANG.setLang(SETTINGS.language)

    def _change(self, language):
        with mock.patch.object(events.Printf, "settings"), \
                mock.patch.object(events.Printf, "enterBool", return_value=False), \
                mock.patch.object(events.Printf, "enter", side_effect=["3", language]), \
                mock.patch.object(events.Printf, "info"), \
                mock.patch.object(SETTINGS, "save"):
            events.changeSettings()

    def test_language_is_stored_as_an_index(self):
        SETTINGS.language = 0
        self._change("2")
        self.assertEqual(SETTINGS.language, 2)

    def test_invalid_language_keeps_the_current_choice(self):
        SETTINGS.language = 1
        for value in ("abc", "999", "", "-1"):
            with self.subTest(value=value):
                self._change(value)
                self.assertEqual(SETTINGS.language, 1)


class SettingsDefaultsTests(TransferFixture, unittest.TestCase):
    def test_bad_settings_use_defaults_without_losing_valid_fields(self):
        path = self.root / 'settings.json'
        path.write_text(json.dumps({'requestIntervalSeconds': 'bad', 'checkExist': 'false',
                                    'downloadPath': '/valid/path', 'videoQuality': '720'}))
        settings = Settings()
        settings.read(str(path))
        self.assertEqual(settings.requestIntervalSeconds, 3.0)
        self.assertFalse(settings.checkExist)
        self.assertEqual(settings.downloadPath, '/valid/path')
        self.assertEqual(settings.videoQuality, VideoQuality.P720)

    def test_fresh_settings_keep_720p(self):
        settings = Settings()
        settings.read(str(self.root / 'missing.json'))
        self.assertEqual(settings.videoQuality, VideoQuality.P720)


class SettingsFileTests(ProfileFixture, unittest.TestCase):
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


class QualityPrioritySettingsTests(CatalogFixtures, unittest.TestCase):
    def test_settings_read_parses_audio_quality_priority(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "settings.json"
            settings_path.write_text(json.dumps({
                "audioQuality": "Atmos",
                "audioQualityPriority": ["Atmos", "High", "HiFi", "Normal"],
                "videoQuality": "P360",
            }), encoding="utf-8")

            settings = Settings()
            settings.read(str(settings_path))

        self.assertEqual(settings.audioQuality, AudioQuality.Atmos)
        self.assertEqual(settings.audioQualityPriority, [
            AudioQuality.Atmos,
            AudioQuality.High,
            AudioQuality.HiFi,
            AudioQuality.Normal,
        ])

    def test_invalid_settings_file_uses_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "settings.json"
            settings_path.write_text("{broken", encoding="utf-8")

            settings = Settings()
            settings.read(str(settings_path))

        self.assertEqual(settings.audioQuality, AudioQuality.Max)
        self.assertEqual(settings.audioQualityPriority, [
            AudioQuality.Max,
            AudioQuality.HiFi,
            AudioQuality.High,
            AudioQuality.Normal,
        ])

    def test_settings_instances_do_not_share_quality_priority(self):
        first = Settings()
        second = Settings()

        first.audioQualityPriority.append(AudioQuality.Atmos)

        self.assertEqual(second.audioQualityPriority, [])

    def test_audio_quality_priority_accepts_user_facing_aliases(self):
        settings = Settings()

        self.assertEqual(settings.getAudioQualityPriority(
            "Dolby Atmos,High (AAC 320),Lossless,Low (AAC 96)"
        ), [
            AudioQuality.Atmos,
            AudioQuality.High,
            AudioQuality.HiFi,
            AudioQuality.Normal,
        ])

    def test_settings_save_serializes_audio_quality_priority_names(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "settings.json"
            settings = Settings()
            settings.read(str(settings_path))
            settings.audioQuality = AudioQuality.Atmos
            settings.audioQualityPriority = [AudioQuality.Atmos, AudioQuality.High, AudioQuality.HiFi]
            settings.save()

            data = json.loads(settings_path.read_text(encoding="utf-8"))

        self.assertEqual(data["audioQuality"], "Atmos")
        self.assertEqual(data["audioQualityPriority"], ["Atmos", "High", "HiFi"])


class AtomicWriteTests(unittest.TestCase):
    def test_atomic_write_replaces_content_and_limits_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text("old", encoding="utf-8")

            _atomicWrite(str(path), "new", mode=0o600)

            self.assertEqual(path.read_text(encoding="utf-8"), "new")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_atomic_write_preserves_old_file_when_replace_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text("known-good", encoding="utf-8")
            with mock.patch("tidal_dl.settings.os.replace", side_effect=OSError("disk failure")):
                with self.assertRaises(OSError):
                    _atomicWrite(str(path), "new")
            self.assertEqual(path.read_text(encoding="utf-8"), "known-good")
            self.assertEqual(list(Path(directory).glob(".tidekeeper-*")), [])


if __name__ == "__main__":
    unittest.main()
