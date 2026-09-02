import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest import mock


def _install_pyside_stub():
    if "PySide6.QtCore" in sys.modules:
        return
    qtcore = ModuleType("PySide6.QtCore")

    class _Signal:
        def __init__(self, *args, **kwargs):
            pass

        def emit(self, *args, **kwargs):
            pass

        def connect(self, *args, **kwargs):
            pass

    class _QObject:
        pass

    class _QRunnable:
        def setAutoDelete(self, *args, **kwargs):
            pass

    def _Slot(*args, **kwargs):
        def decorator(fn):
            return fn
        return decorator

    qtcore.QObject = _QObject
    qtcore.QRunnable = _QRunnable
    qtcore.Signal = _Signal
    qtcore.Slot = _Slot
    pyside = ModuleType("PySide6")
    pyside.QtCore = qtcore
    sys.modules["PySide6"] = pyside
    sys.modules["PySide6.QtCore"] = qtcore


class NestedGuiProgressTests(unittest.TestCase):
    def setUp(self):
        _install_pyside_stub()
        from tidal_dl.gui_app.workers import ItemProgressReporter
        self.snapshots = []
        self.reporter = ItemProgressReporter(
            "item",
            lambda item, snap: self.snapshots.append(dict(snap)),
        )

    def test_nested_album_then_videos_does_not_jump_to_100(self):
        from tidal_dl.gui_app.backend import queue_progress_percent

        self.reporter.begin_collection(10)
        for index in range(10):
            self.reporter.begin_entry(index + 1, 10, f"t{index}")
            self.reporter.finish_entry(index + 1, 10, True)
        self.assertEqual(self.reporter.count, 10)
        self.assertEqual(self.reporter.completed, 10)

        self.reporter.begin_collection(2)
        self.assertEqual(self.reporter.count, 12)
        self.reporter.begin_entry(1, 2, "video")
        self.assertEqual(self.reporter.count, 12)
        percent = queue_progress_percent(self.reporter.snapshot())
        self.assertLess(percent, 100)
        self.assertGreaterEqual(percent, 80)

        self.reporter.finish_entry(1, 2, True)
        self.reporter.begin_entry(2, 2, "video2")
        self.reporter.finish_entry(2, 2, True)
        self.assertEqual(self.reporter.count, 12)
        self.assertEqual(self.reporter.completed, 12)
        self.assertEqual(queue_progress_percent(self.reporter.snapshot()), 100)


class RuntimeSettingsTests(unittest.TestCase):
    def _values(self, **overrides):
        values = {
            "downloadPath": "/tmp/tidekeeper-dl",
            "audioQuality": "HiFi",
            "videoQuality": "P720",
            "audioQualityPriority": ["HiFi", "High"],
            "checkExist": True,
            "includeEP": True,
            "saveCovers": True,
            "lyricFile": False,
            "saveAlbumInfo": False,
            "downloadVideos": True,
            "multiThread": False,
            "downloadDelay": True,
            "requestIntervalSeconds": 3.0,
            "adaptiveRateLimit": True,
            "saveAsFlac": True,
            "usePlaylistFolder": True,
            "showProgress": True,
            "showTrackInfo": True,
            "language": 0,
            "albumFolderFormat": "{AlbumTitle}",
            "playlistFolderFormat": "{PlaylistName}",
            "trackFileFormat": "{TrackTitle}",
            "videoFileFormat": "{VideoTitle}",
            "apiKeyIndex": 1,
        }
        values.update(overrides)
        return values

    def test_apply_runtime_settings_does_not_persist_or_logout(self):
        from tidal_dl.enums import AudioQuality
        from tidal_dl.gui_app.backend import TidekeeperBackend
        from tidal_dl.settings import SETTINGS

        backend = TidekeeperBackend()
        old = {
            "audioQuality": SETTINGS.audioQuality,
            "apiKeyIndex": SETTINGS.apiKeyIndex,
            "saveAsFlac": SETTINGS.saveAsFlac,
            "downloadPath": SETTINGS.downloadPath,
        }
        SETTINGS.apiKeyIndex = 4
        try:
            with mock.patch.object(SETTINGS, "save") as save, \
                 mock.patch("tidal_dl.gui_app.backend.logout") as logout, \
                 mock.patch("tidal_dl.gui_app.backend.syncPlaybackRateLimiter"):
                result = backend.apply_runtime_settings(self._values())
            save.assert_not_called()
            logout.assert_not_called()
            self.assertFalse(result.get("reauth_required"))
            self.assertEqual(SETTINGS.audioQuality, AudioQuality.HiFi)
            self.assertTrue(SETTINGS.saveAsFlac)
            self.assertEqual(SETTINGS.apiKeyIndex, 4)
        finally:
            for key, value in old.items():
                setattr(SETTINGS, key, value)

    def test_save_settings_still_logs_out_on_client_change(self):
        from tidal_dl.gui_app.backend import TidekeeperBackend
        from tidal_dl.settings import SETTINGS

        backend = TidekeeperBackend()
        old_index = SETTINGS.apiKeyIndex
        SETTINGS.apiKeyIndex = 4
        try:
            with mock.patch.object(SETTINGS, "save"), \
                 mock.patch("tidal_dl.gui_app.backend.logout") as logout, \
                 mock.patch("tidal_dl.gui_app.backend.syncPlaybackRateLimiter"), \
                 mock.patch("tidal_dl.gui_app.backend.LANG.setLang"), \
                 mock.patch("tidal_dl.gui_app.backend.apiKey.getItem", return_value={"clientId": "x"}):
                result = backend.save_settings(self._values(apiKeyIndex=1))
            logout.assert_called_once()
            self.assertTrue(result.get("reauth_required"))
        finally:
            SETTINGS.apiKeyIndex = old_index


if __name__ == "__main__":
    unittest.main()
