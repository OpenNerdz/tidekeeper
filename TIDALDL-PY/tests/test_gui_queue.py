import os
import unittest
import copy
from unittest import mock
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
        from tidal_dl.settings import SETTINGS
        self.old_settings = copy.deepcopy(SETTINGS.__dict__)
        from tidal_dl.enums import Type
        from tidal_dl.gui_app.backend import DemoBackend, SearchItem
        from tidal_dl.gui_app.main_window import MainWindow

        self.backend = DemoBackend()
        self.backend.initialize()
        self.window = MainWindow(self.backend)
        self.SearchItem = SearchItem
        self.Type = Type

    def tearDown(self):
        from tidal_dl.settings import SETTINGS
        self.window.download_in_progress = False
        self.window.close()
        SETTINGS.__dict__.clear()
        SETTINGS.__dict__.update(self.old_settings)

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

    def test_completed_result_can_be_queued_again(self):
        item = self.backend.search('song', self.Type.Track)[0]
        self.window.set_search_results([item])
        self.window.results_table.selectRow(0)
        self.window.add_selected_to_queue()
        self.window.queue[0].status = 'Done'
        self.window.clear_queue()
        self.window.add_selected_to_queue()
        self.assertEqual(item.status, 'Queued')
        self.assertEqual(len(self.window.pending_queue_items()), 1)
        self.assertIsNot(self.window.queue[0], item)

    def test_sorted_status_update_keeps_progress_with_correct_job(self):
        from PySide6.QtCore import Qt
        first, second = self.backend.search('song', self.Type.Track)[:2]
        self.window.queue = [first, second]
        self.window.refresh_queue_table()
        self.window.queue_table.sortItems(4, Qt.AscendingOrder)
        self.window._set_queue_item_status(second, 'Done')
        for row in range(2):
            item = self.window._row_item(self.window.queue_table, row)
            expected = '100%' if item is second else ''
            self.assertEqual(self.window.queue_table.item(row, 5).text(), expected)

    def test_audio_selection_controls_effective_priority(self):
        from tidal_dl.enums import AudioQuality
        from tidal_dl.gui_app.backend import TidekeeperBackend
        from tidal_dl.settings import SETTINGS
        from tidal_dl.tidal import TIDAL_API
        self.window.audio_quality.setCurrentText('Atmos')
        values = self.window.collect_settings_values()
        self.assertEqual(values['audioQualityPriority'][0], 'Atmos')
        self.assertIn('Atmos', self.window.priority_preview.text())
        with mock.patch.object(SETTINGS, 'save'), mock.patch.object(TIDAL_API, 'apiKey'), \
             mock.patch('tidal_dl.gui_app.backend.logout'):
            TidekeeperBackend().save_settings(values)
        self.assertEqual(SETTINGS.audioQuality, AudioQuality.Atmos)
        self.assertEqual(SETTINGS.getDownloadAudioQualityPriority()[0], AudioQuality.Atmos)

    def test_applying_download_options_does_not_save_or_change_client(self):
        from tidal_dl.gui_app.backend import TidekeeperBackend
        from tidal_dl.settings import SETTINGS
        from tidal_dl.tidal import TIDAL_API
        values = self.window.collect_settings_values()
        values['apiKeyIndex'] = SETTINGS.apiKeyIndex
        with mock.patch.object(SETTINGS, 'save') as save, mock.patch.object(TIDAL_API, 'apiKey'):
            TidekeeperBackend().apply_download_settings(values)
            save.assert_not_called()
            values['apiKeyIndex'] += 1
            with self.assertRaisesRegex(ValueError, 'sign in again'):
                TidekeeperBackend().apply_download_settings(values)

    def test_album_and_video_progress_share_totals(self):
        from tidal_dl.gui_app.workers import ItemProgressReporter
        from tidal_dl.gui_app.backend import queue_progress_percent
        reporter = ItemProgressReporter(None, lambda *args: None)
        reporter.plan_collection(12)
        reporter.begin_collection(10)
        for index in range(1, 11):
            reporter.begin_entry(index, 10)
            reporter.finish_entry(index, 10)
        self.assertEqual(queue_progress_percent(reporter.snapshot()), 83)
        reporter.begin_collection(2)
        reporter.begin_entry(1, 2)
        reporter.for_entry(1).setMaxNum(10)
        reporter.for_entry(1).addCurNum(5)
        self.assertEqual(reporter.snapshot()['count'], 12)
        self.assertEqual(reporter.snapshot()['completed'], 10)
        self.assertEqual(queue_progress_percent(reporter.snapshot()), 87)

    def test_parallel_progress_keeps_separate_file_counters(self):
        from tidal_dl.gui_app.workers import ItemProgressReporter
        from tidal_dl.gui_app.backend import queue_progress_percent
        reporter = ItemProgressReporter(None, lambda *args: None)
        reporter.begin_collection(2)
        reporter.begin_entry(1, 2)
        first = reporter.for_entry(1)
        reporter.begin_entry(2, 2)
        second = reporter.for_entry(2)
        first.setMaxNum(10)
        second.setMaxNum(100)
        first.addCurNum(10)
        second.addCurNum(50)
        self.assertEqual(queue_progress_percent(reporter.snapshot()), 75)
        reporter.finish_entry(1, 2)
        self.assertEqual(queue_progress_percent(reporter.snapshot()), 75)
        self.assertEqual(reporter.snapshot()['bytes_total'], 100)

    def test_logout_stops_polling_and_ignores_late_success(self):
        from tidal_dl.gui_app.backend import AuthStatus
        self.window.login_polling = True
        self.window.poll_timer.start(10000)
        self.window.logout()
        self.assertFalse(self.window.poll_timer.isActive())
        self.assertFalse(self.window.login_polling)
        self.window._device_login_polled(AuthStatus('late', 'US', 0, True, fresh_login=True))
        self.assertNotIn('Login complete.', self.window.account_log.toPlainText())

    def test_active_download_locks_settings_and_account_controls(self):
        self.window.download_in_progress = True
        self.window.update_action_states()
        self.assertFalse(self.window.pages['settings'].isEnabled())
        self.assertFalse(self.window.pages['account'].isEnabled())
        self.window._download_finished()
        self.assertTrue(self.window.pages['settings'].isEnabled())
        self.assertTrue(self.window.pages['account'].isEnabled())

    def test_queue_displays_downloaded_quality(self):
        item = self.backend.search('song', self.Type.Track)[0]
        self.window.queue = [item]
        self.window.refresh_queue_table()
        self.window._set_queue_item_status(item, 'Downloading')
        self.window._set_queue_item_progress(item, {'actual_quality': 'HIGH (aac)'})
        self.assertEqual(self.window.queue_table.item(0, 3).text(), 'HIGH (aac)')

    def test_close_cancels_transfer_before_exiting(self):
        self.window.download_in_progress = True
        self.window.download_worker = mock.Mock()
        event = mock.Mock()
        self.window.closeEvent(event)
        self.window.download_worker.cancel.assert_called_once()
        event.ignore.assert_called_once()
        event.accept.assert_not_called()


if __name__ == "__main__":
    unittest.main()
