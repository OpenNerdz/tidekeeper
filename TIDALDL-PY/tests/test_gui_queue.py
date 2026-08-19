import os
import unittest
from types import SimpleNamespace

try:
    from PySide6.QtWidgets import QApplication
except ImportError:  # pragma: no cover - GUI extra not installed
    QApplication = None


@unittest.skipIf(QApplication is None, "PySide6 is not installed")
class GuiQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from tidal_dl.enums import Type
        from tidal_dl.gui_app.backend import DemoBackend, SearchItem
        from tidal_dl.gui_app.main_window import MainWindow

        self.backend = DemoBackend()
        self.backend.initialize()
        self.window = MainWindow(self.backend)
        self.SearchItem = SearchItem
        self.Type = Type

    def tearDown(self):
        self.window.close()

    def test_direct_paste_creates_separate_queue_rows(self):
        self.window.direct_text.setPlainText(
            "https://tidal.com/browse/track/1\n"
            "https://tidal.com/browse/track/2\n"
        )
        self.window.add_direct_to_queue()

        self.assertEqual(len(self.window.queue), 2)
        self.assertEqual(self.window.queue[0].source, "https://tidal.com/browse/track/1")
        self.assertEqual(self.window.queue[1].source, "https://tidal.com/browse/track/2")
        self.assertEqual(self.window.queue_table.rowCount(), 2)

    def test_retry_failed_restarts_only_failed_rows(self):
        done = self.SearchItem(self.Type.Track, "Done", "", "", "1", "", SimpleNamespace(id=1), status="Done")
        failed = self.SearchItem(self.Type.Track, "Failed", "", "", "2", "", SimpleNamespace(id=2), status="Failed")
        queued = self.SearchItem(self.Type.Track, "Queued", "", "", "3", "", SimpleNamespace(id=3), status="Queued")
        self.window.queue = [done, failed, queued]
        self.window.refresh_queue_table()

        self.assertTrue(self.window.retry_failed_button.isEnabled())
        self.assertEqual(self.window.failed_queue_items(), [failed])
        self.assertEqual(self.window.pending_queue_items(), [failed, queued])

        started = []

        def capture(items):
            started.extend(items)

        self.window.start_downloads = capture
        self.window.retry_failed_downloads()

        self.assertEqual(started, [failed])
        self.assertEqual(failed.status, "Queued")
        self.assertEqual(done.status, "Done")
        self.assertEqual(queued.status, "Queued")

    def test_start_queue_skips_completed_rows(self):
        done = self.SearchItem(self.Type.Track, "Done", "", "", "1", "", SimpleNamespace(id=1), status="Done")
        queued = self.SearchItem(self.Type.Track, "Queued", "", "", "3", "", SimpleNamespace(id=3), status="Queued")
        self.window.queue = [done, queued]
        self.window.refresh_queue_table()

        started = []
        self.window.start_downloads = started.extend
        self.window.start_queue_download()
        self.assertEqual(started, [queued])

    def test_device_login_poll_ignores_preexisting_token(self):
        from tidal_dl.gui_app.backend import AuthStatus

        self.window.login_polling = True
        self.window.device_login_button.setEnabled(False)
        stale = AuthStatus("old-user", "US", 0, True, fresh_login=False)
        self.window._device_login_polled(stale)
        self.assertTrue(self.window.login_polling)
        self.assertFalse(self.window.device_login_button.isEnabled())

        fresh = AuthStatus("new-user", "US", 0, True, fresh_login=True)
        self.window._device_login_polled(fresh)
        self.assertFalse(self.window.login_polling)
        self.assertTrue(self.window.device_login_button.isEnabled())
        self.assertIn("Login complete.", self.window.account_log.toPlainText())

    def test_progress_updates_status_and_percent(self):
        item = self.SearchItem(self.Type.Album, "Album", "Artist", "HI_RES", "9", "", SimpleNamespace(id=9))
        item.status = "Downloading"
        self.window.queue = [item]
        self.window.refresh_queue_table()
        self.window._set_queue_item_progress(item, {
            "completed": 3,
            "count": 12,
            "current": 4,
            "bytes": 0,
            "bytes_total": 0,
            "speed": 2 * 1024 * 1024,
            "eta": 12,
        })

        self.assertEqual(item.progress_percent, 25)
        self.assertIn("4/12", item.progress_label)
        status_cell = self.window.queue_table.item(0, 4)
        progress_cell = self.window.queue_table.item(0, 5)
        self.assertIn("Downloading 4/12", status_cell.text())
        self.assertEqual(progress_cell.text(), "25%")


if __name__ == "__main__":
    unittest.main()
