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

    def test_retry_marks_legacy_failed_artist_for_log_lookup(self):
        artist = self.SearchItem(self.Type.Artist, 'Artist', '', '', '42', '', None, status='Failed')
        cancelled = self.SearchItem(self.Type.Artist, 'Cancelled', '', '', '43', '', None, status='Cancelled')
        self.window.queue = [artist, cancelled]
        with mock.patch.object(self.window, 'start_downloads'):
            self.window.retry_failed_downloads()
        self.assertTrue(artist.legacy_retry_from_log)
        self.assertFalse(cancelled.legacy_retry_from_log)

    def test_start_queue_skips_completed_rows(self):
        done = self.SearchItem(self.Type.Track, "Done", "", "", "1", "", SimpleNamespace(id=1), status="Done")
        queued = self.SearchItem(self.Type.Track, "Queued", "", "", "3", "", SimpleNamespace(id=3), status="Queued")
        self.window.queue = [done, queued]
        self.window.refresh_queue_table()

        started = []
        self.window.start_downloads = started.extend
        self.window.start_queue_download()
        self.assertEqual(started, [queued])

    def test_queue_removal_slots_preserve_items_during_download(self):
        item = self.SearchItem(self.Type.Track, 'Active', '', '', '1', '', None, status='Downloading')
        self.window.queue = [item]
        self.window.refresh_queue_table()
        self.window.queue_table.selectRow(0)
        self.window.download_in_progress = True
        # Delete invokes the removal slot directly even when its button is disabled.
        self.window.remove_selected_queue_items()
        self.window.clear_queue()
        self.assertEqual(self.window.queue, [item])
        self.assertEqual(self.window.queue_table.rowCount(), 1)
        self.window.download_in_progress = False
        self.window.remove_selected_queue_items()
        self.assertEqual(self.window.queue, [])

    def test_live_queued_items_ignore_active_failed_and_done(self):
        done = self.SearchItem(self.Type.Track, "Done", "", "", "1", "", SimpleNamespace(id=1), status="Done")
        failed = self.SearchItem(self.Type.Track, "Failed", "", "", "2", "", SimpleNamespace(id=2), status="Failed")
        downloading = self.SearchItem(self.Type.Track, "Downloading", "", "", "3", "", SimpleNamespace(id=3), status="Downloading")
        queued = self.SearchItem(self.Type.Track, "Queued", "", "", "4", "", SimpleNamespace(id=4), status="Queued")
        self.window.queue = [done, failed, downloading, queued]
        self.assertEqual(self.window._live_queued_items(), [queued])

    def test_start_downloads_asks_worker_for_items_added_later(self):
        queued = self.SearchItem(self.Type.Track, "Queued", "", "", "3", "", SimpleNamespace(id=3), status="Queued")
        captured = {}

        class FakeWorker:
            def __init__(self, backend, items, more_items=None):
                captured["items"] = list(items)
                captured["more_items"] = more_items
                self.signals = SimpleNamespace(
                    log=SimpleNamespace(connect=lambda *_: None),
                    item_status=SimpleNamespace(connect=lambda *_: None),
                    item_progress=SimpleNamespace(connect=lambda *_: None),
                    item_detail=SimpleNamespace(connect=lambda *_: None),
                    result=SimpleNamespace(connect=lambda *_: None),
                    error=SimpleNamespace(connect=lambda *_: None),
                    finished=SimpleNamespace(connect=lambda *_: None),
                )

        self.window.start_worker = lambda worker: None
        import tidal_dl.gui_app.main_window as main_window

        original = main_window.DownloadWorker
        main_window.DownloadWorker = FakeWorker
        try:
            self.window.start_downloads([queued])
        finally:
            main_window.DownloadWorker = original

        self.assertEqual(captured["items"], [queued])
        self.assertEqual(captured["more_items"], self.window._live_queued_items)

    def test_catalog_selection_and_equivalent_links_share_one_unfinished_job(self):
        item = self.backend.search('song', self.Type.Track)[0]
        self.window.set_search_results([item])
        self.window.results_table.selectRow(0)
        self.window.add_selected_to_queue()
        self.window.add_selected_to_queue()
        self.window.direct_text.setPlainText(f'https://tidal.com/browse/track/{item.identifier}?share=1')
        self.window.add_direct_to_queue()
        self.assertEqual(len(self.window.queue), 1)
        self.assertIn('already in the queue', self.window.queue_status.toolTip())
        with mock.patch.object(self.window, 'start_downloads') as start:
            self.window.download_direct()
        start.assert_called_once_with(self.window.queue)
        self.window.queue[0].status = 'Done'
        self.window.add_selected_to_queue()
        self.assertEqual([row.status for row in self.window.queue], ['Done', 'Queued'])

    def test_audio_and_video_only_collections_are_distinct_jobs(self):
        from tidal_dl.gui_app.backend import queue_item
        item = self.backend.search('album', self.Type.Album)[0]
        jobs = self.window._enqueue_items([queue_item(item), queue_item(item, video_only=True)])
        self.assertEqual(len(jobs), 2)

    def test_sorted_removal_undo_restores_order_and_preserves_new_jobs(self):
        from PySide6.QtCore import Qt
        original = self.backend.search('song', self.Type.Track)[:3]
        self.window.queue = list(original)
        self.window.refresh_queue_table()
        self.window.queue_table.sortItems(1, Qt.DescendingOrder)
        self.window.queue_table.selectRow(1)
        removed = self.window._row_item(self.window.queue_table, 1)
        self.window.remove_selected_queue_items()
        self.assertNotIn(removed, self.window.queue)
        added = self.backend.direct_item('https://tidal.com/browse/track/123')
        self.window._enqueue_items([added])
        self.window.undo_queue_removal()
        self.assertEqual(self.window.queue, original + [added])
        self.assertFalse(self.window.undo_queue_button.isEnabled())

    def test_undo_does_not_duplicate_readded_unfinished_jobs(self):
        from tidal_dl.gui_app.backend import queue_item
        item = self.backend.search('song', self.Type.Track)[0]
        self.window._enqueue_items([item])
        self.window.clear_queue()
        replacement = queue_item(item)
        self.window._enqueue_items([replacement])
        self.window.undo_queue_removal()
        self.assertEqual(self.window.queue, [replacement])

    def test_clear_done_keeps_incomplete_jobs_and_supports_undo(self):
        items = self.backend.search('song', self.Type.Track)[:3]
        items[0].status, items[1].status = 'Done', 'Failed'
        self.window.queue = list(items)
        self.window.refresh_queue_table()
        self.window.download_log.setPlainText('Retain diagnostic history')
        self.window.clear_completed_queue_items()
        self.assertEqual(self.window.queue, items[1:])
        self.assertIn('Retain diagnostic history', self.window.download_log.toPlainText())
        self.window.undo_queue_removal()
        self.assertEqual(self.window.queue, items)

    def test_retry_incomplete_resets_attempt_state_and_keeps_new_jobs(self):
        items = self.backend.search('song', self.Type.Track)[:6]
        statuses = ['Failed', 'Partial', 'Interrupted', 'Cancelled', 'Done', 'Queued']
        for item, status in zip(items, statuses):
            item.status = status
            item.status_detail = 'Previous attempt'
            item.actual_quality = 'LOW'
            item.progress_percent = 50
        self.window.queue = items
        self.window.refresh_queue_table()
        with mock.patch.object(self.window, 'start_downloads') as start:
            self.window.retry_failed_downloads()
        start.assert_called_once_with(items[:4])
        for item in items[:4]:
            self.assertEqual((item.status, item.status_detail, item.actual_quality, item.progress_percent),
                             ('Queued', '', '', 0))
        self.assertEqual([item.status for item in items[4:]], ['Done', 'Queued'])

    def test_failure_details_are_visible_selectable_and_redacted(self):
        from PySide6.QtCore import Qt
        item = self.backend.search('song', self.Type.Track)[0]
        self.window._enqueue_items([item])
        self.window._set_queue_item_detail(item, 'Cannot load stream: access_token=dummy-secret')
        self.window._set_queue_item_status(item, 'Failed')
        self.window.queue_table.selectRow(0)
        self.assertFalse(self.window.queue_detail.isHidden())
        self.assertNotIn('dummy-secret', self.window.queue_detail.text())
        self.assertIn('Cannot load stream', self.window.queue_detail.text())
        self.assertEqual(self.window.queue_detail.textFormat(), Qt.PlainText)
        self.assertEqual(self.window.queue_table.item(0, 4).toolTip(), item.status_detail)
        self.window._set_queue_item_status(item, 'Downloading')
        self.assertEqual(item.status_detail, '')
        self.assertTrue(self.window.queue_detail.isHidden())

    def test_settings_dirty_save_and_reload_preserve_enum_types(self):
        from tidal_dl.enums import AudioQuality, VideoQuality
        from tidal_dl.settings import SETTINGS
        self.assertFalse(self.window.save_settings_button.isEnabled())
        self.window.audio_quality.setCurrentText('HiFi')
        self.assertTrue(self.window.save_settings_button.isEnabled())
        self.assertEqual(self.window.settings_status.text(), 'Unsaved changes')
        self.window.save_settings()
        self.assertEqual(SETTINGS.audioQuality, AudioQuality.HiFi)
        self.assertIsInstance(SETTINGS.videoQuality, VideoQuality)
        self.assertFalse(self.window.save_settings_button.isEnabled())
        saved = self.window.collect_settings_values()
        self.window.audio_quality.setCurrentText('Normal')
        self.window.apply_settings_for_download()
        self.window.reload_settings()
        self.assertEqual(self.window.collect_settings_values(), saved)
        self.assertFalse(self.window.save_settings_button.isEnabled())

    def test_failed_settings_save_keeps_unsaved_indicator(self):
        self.window.download_path.setText('/new/path')
        with mock.patch.object(self.backend, 'save_settings', side_effect=OSError('Disk full')):
            self.window.save_settings()
        self.assertEqual(self.window.settings_status.text(), 'Disk full')
        self.assertTrue(self.window.save_settings_button.isEnabled())
        self.assertIn('•', self.window.settings_toggle.text())

    def test_cancel_search_keeps_previous_results_and_suppresses_late_callbacks(self):
        original = self.backend.search('song', self.Type.Track)[:1]
        self.window.set_search_results(original)
        self.window.search_text.setText('new search')
        with mock.patch.object(self.window, 'start_worker'):
            self.window.run_search()
        worker = self.window.search_worker
        self.assertEqual(self.window.search_button.text(), 'Cancel')
        self.window.run_search()
        self.assertFalse(self.window.search_button.isEnabled())
        worker.signals.result.emit([])
        worker.signals.error.emit('An obsolete failure')
        worker.signals.finished.emit()
        self.assertEqual(self.window.results, original)
        self.assertEqual(self.window.search_status.text(), 'Search cancelled')
        self.assertEqual(self.window.search_button.text(), 'Search')
        self.assertTrue(self.window.search_button.isEnabled())

    def test_search_results_sort_duration_by_elapsed_time(self):
        from PySide6.QtCore import Qt
        items = self.backend.search('song', self.Type.Track)[:3]
        for item, duration in zip(items, ('1:00:24', '2:17', '2:21:31')):
            item.duration = duration
        self.window.set_search_results(items)

        self.window.results_table.sortItems(4, Qt.AscendingOrder)
        ascending = [self.window.results_table.item(row, 4).text() for row in range(3)]
        self.assertEqual(ascending, ['2:17', '1:00:24', '2:21:31'])

        self.window.results_table.sortItems(4, Qt.DescendingOrder)
        descending = [self.window.results_table.item(row, 4).text() for row in range(3)]
        self.assertEqual(descending, ['2:21:31', '1:00:24', '2:17'])

    def test_search_and_download_failures_use_inline_feedback(self):
        with mock.patch('tidal_dl.gui_app.main_window.QMessageBox.warning') as warning:
            self.window.show_search_error('Connection timed out')
            self.window.show_download_error('One download failed')
        warning.assert_not_called()
        self.assertEqual(self.window.search_status.toolTip(), 'Connection timed out')
        self.assertTrue(self.window.log_toggle.isChecked())
        self.assertIn('One download failed', self.window.download_log.toPlainText())

    def test_failed_real_settings_save_restores_runtime_and_preserves_session(self):
        from tidal_dl.gui_app.backend import TidekeeperBackend
        from tidal_dl.settings import SETTINGS
        from tidal_dl.tidal import TIDAL_API
        saved = copy.deepcopy(SETTINGS.__dict__)
        client = TIDAL_API.apiKey
        values = self.window.collect_settings_values()
        values['apiKeyIndex'] += 1
        values['downloadPath'] = '/new/path'
        with mock.patch.object(SETTINGS, 'save', side_effect=OSError('Disk full')), \
             mock.patch('tidal_dl.gui_app.backend.logout') as logout:
            with self.assertRaisesRegex(OSError, 'Disk full'):
                TidekeeperBackend().save_settings(values)
        self.assertEqual(SETTINGS.__dict__, saved)
        self.assertIs(TIDAL_API.apiKey, client)
        logout.assert_not_called()

    def test_narrow_inspector_layout_preserves_titles_and_restores_columns(self):
        self.window.resize(1024, 620)
        self.window.show()
        self.window.show_screen('settings')
        self.app.processEvents()
        self.assertGreaterEqual(self.window.settings_status.width(), 120)
        for table in (self.window.results_table, self.window.queue_table):
            self.assertGreaterEqual(table.columnWidth(1), 140)
            self.assertEqual(table.horizontalScrollBar().maximum(), 0)
        self.assertTrue(self.window.results_table.isColumnHidden(5))
        self.assertTrue(self.window.queue_table.isColumnHidden(2))
        self.window.show_screen('workspace')
        self.window.resize(1180, 760)
        self.app.processEvents()
        self.assertFalse(self.window.results_table.isColumnHidden(5))
        self.assertFalse(self.window.queue_table.isColumnHidden(2))

    def _wait_for_workers(self):
        from PySide6.QtTest import QTest
        for _ in range(300):
            self.app.processEvents()
            if not self.window.active_workers:
                return
            QTest.qWait(10)
        self.fail('GUI workers did not finish within three seconds')

    def test_real_qt_workers_complete_search_and_partial_download(self):
        from PySide6.QtCore import QThread
        class WarningBackend:
            def download(self, item, log, progress):
                progress.note_warning('Cover could not be saved')
        delivered_threads = []
        set_results = self.window.set_search_results
        def record_results(*args):
            delivered_threads.append(QThread.currentThread())
            set_results(*args)
        self.window.set_search_results = record_results
        self.window.search_text.setText('song')
        self.window.run_search()
        self._wait_for_workers()
        self.assertTrue(self.window.results)
        self.assertEqual(delivered_threads, [self.app.thread()])
        self.assertFalse(self.window.search_in_progress)
        self.window.results_table.selectRow(0)
        self.window.add_selected_to_queue()
        with mock.patch.object(self.backend, 'download', side_effect=WarningBackend().download):
            self.window.start_queue_download()
            self._wait_for_workers()
        self.assertEqual(self.window.queue[0].status, 'Partial')
        self.assertEqual(self.window.queue[0].status_detail, 'Cover could not be saved')
        self.assertTrue(self.window.log_toggle.isChecked())
        self.assertIn('needs attention', self.window.queue_status.toolTip())
        self.assertFalse(self.window.download_in_progress)

    def test_real_qt_search_cancel_interrupts_cooperative_wait(self):
        from threading import Event
        from PySide6.QtTest import QTest
        from tidal_dl.runtime import sleep
        entered = Event()
        def slow_search(*args):
            entered.set()
            sleep(10)
            return []
        self.window.search_text.setText('song')
        with mock.patch.object(self.backend, 'search', side_effect=slow_search):
            self.window.run_search()
            try:
                for _ in range(100):
                    if entered.is_set():
                        break
                    QTest.qWait(10)
                self.assertTrue(entered.is_set())
            finally:
                self.window.cancel_search()
                self._wait_for_workers()
        self.assertEqual(self.window.search_status.text(), 'Search cancelled')
        self.assertFalse(self.window.search_in_progress)

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

    def test_nested_album_video_progress_keeps_combined_count(self):
        from tidal_dl.gui_app.backend import queue_progress_percent
        from tidal_dl.gui_app.workers import ItemProgressReporter

        reporter = ItemProgressReporter("album", lambda *_: None)
        reporter.begin_collection(10)
        for index in range(1, 11):
            reporter.begin_entry(index, 10)
            reporter.finish_entry(index, 10, True)
        reporter.begin_collection(2)
        reporter.begin_entry(1, 2)

        self.assertEqual(reporter.count, 12)
        self.assertEqual(reporter.completed, 10)
        self.assertLess(queue_progress_percent(reporter.snapshot()), 100)


    def test_download_apply_does_not_save_or_logout(self):
        saved = []
        logged_out = []
        original_save = self.backend.save_settings

        def wrapped(values):
            saved.append(values)
            return original_save(values)

        self.backend.save_settings = wrapped
        self.backend.logout = lambda: logged_out.append(True)
        self.window.apply_settings_for_download()
        self.assertEqual(saved, [])
        self.assertEqual(logged_out, [])

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

    def test_quality_menu_excludes_master_and_preserves_legacy_profile_fallbacks(self):
        from tidal_dl.enums import AUDIO_QUALITY_ORDER, AudioQuality
        from tidal_dl.settings import SETTINGS
        self.assertEqual(
            [self.window.audio_quality.itemData(i) for i in range(self.window.audio_quality.count())],
            [quality.name for quality in AUDIO_QUALITY_ORDER],
        )
        cases = [
            ([], ['Max', 'HiFi']),
            ([AudioQuality.Master], ['Max', 'HiFi']),
            ([AudioQuality.Master, AudioQuality.Max, AudioQuality.High], ['Max', 'High']),
        ]
        for saved, expected in cases:
            with self.subTest(saved=saved):
                SETTINGS.audioQuality = AudioQuality.Master
                SETTINGS.audioQualityPriority = saved
                self.window.refresh_settings()
                values = self.window.collect_settings_values()
                self.assertEqual(values['audioQuality'], 'Max')
                self.assertEqual(values['audioQualityPriority'], expected)
                # Displaying migrated settings must not write or mutate the profile.
                self.assertEqual(SETTINGS.audioQuality, AudioQuality.Master)
                self.assertEqual(SETTINGS.audioQualityPriority, saved)

    def test_client_menu_uses_saved_ids_not_list_offsets(self):
        from tidal_dl.settings import SETTINGS
        self.assertEqual([self.window.api_client.itemData(i)
                          for i in range(self.window.api_client.count())], [1, 4, 5])
        for index in (1, 4, 5):
            SETTINGS.apiKeyIndex = index
            self.window.refresh_settings()
            self.assertEqual(self.window.collect_settings_values()['apiKeyIndex'], index)

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

    def test_logout_dispatches_remote_revocation_without_waiting(self):
        from tidal_dl.gui_app.backend import TidekeeperBackend
        from tidal_dl.tidal import TIDAL_API

        with mock.patch.object(self.backend, 'logout', lambda: TidekeeperBackend.logout(self.backend)), \
                mock.patch.object(TIDAL_API, 'clearSavedSession') as clear, \
                mock.patch.object(TIDAL_API.key, 'accessToken', 'old-access'), \
                mock.patch.object(self.backend, 'revoke_session', return_value=True) as revoke, \
                mock.patch.object(self.window, 'start_worker') as start:
            self.window.logout()
            clear.assert_called_once_with()
            revoke.assert_not_called()
            self.assertIn('Logged out.', self.window.account_log.toPlainText())
            worker = start.call_args.args[0]
            worker.run()
            revoke.assert_called_once_with('old-access')

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

    def test_queue_summary_distinguishes_stopped_and_partial_items(self):
        items = self.backend.search('song', self.Type.Track)[:4]
        for item, status in zip(items, ('Queued', 'Partial', 'Cancelled', 'Interrupted')):
            item.status = status
        self.window.queue = items
        self.window.refresh_queue_table()
        text = self.window.queue_status.text()
        for label in ('1 queued', '1 partial', '1 cancelled', '1 interrupted'):
            self.assertIn(label, text)
        self.assertNotIn('4 queued', text)

    def test_queue_errors_escape_markup(self):
        self.window._set_queue_message('Failed <album> & retry')
        self.assertIn('&lt;album&gt; &amp; retry', self.window.queue_status.text())

    def test_retry_resets_previous_progress_and_quality(self):
        item = self.backend.search('song', self.Type.Track)[0]
        item.status = 'Partial'
        item.progress_percent = 75
        item.actual_quality = 'old quality'
        self.window.queue = [item]
        self.window.refresh_queue_table()
        self.window._set_queue_item_status(item, 'Downloading')
        self.assertEqual(item.progress_percent, 0)
        self.assertEqual(item.actual_quality, '')

    def test_logs_are_plain_text_and_bounded(self):
        self.window.account_log.append('<b>literal log text</b>')
        self.assertIn('<b>literal log text</b>', self.window.account_log.toPlainText())
        for index in range(2100):
            self.window.account_log.append(str(index))
        self.assertLessEqual(self.window.account_log.document().blockCount(), 2000)

    def test_download_log_preserves_scroll_position(self):
        self.window.show()
        self.window.log_toggle.setChecked(True)
        self.window.append_download_log('line\n' * 1000)
        self.app.processEvents()
        scrollbar = self.window.download_log.verticalScrollBar()
        self.assertGreater(scrollbar.maximum(), 0)
        scrollbar.setValue(0)
        self.window.append_download_log('next line\n')
        self.assertEqual(scrollbar.value(), 0)

    def test_reload_settings_reads_backend(self):
        with mock.patch.object(self.backend, 'reload_settings', return_value={}) as reload:
            self.window.reload_settings()
            reload.assert_called_once_with()

    def test_empty_search_explains_no_matches(self):
        self.window.set_search_results([])
        self.assertIn('No results', self.window.results_empty._label.text())


if __name__ == "__main__":
    unittest.main()
