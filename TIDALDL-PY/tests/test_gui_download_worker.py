import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock


def _install_pyside_stub():
    if "PySide6.QtCore" in sys.modules:
        return
    qtcore = ModuleType("PySide6.QtCore")

    class _Signal:
        def __init__(self, *args, **kwargs):
            self._slots = []

        def emit(self, *args, **kwargs):
            for slot in self._slots:
                slot(*args, **kwargs)

        def connect(self, slot, *args, **kwargs):
            self._slots.append(slot)

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


class RecordingBackend:
    def __init__(self, on_download=None):
        self.downloaded = []
        self._on_download = on_download

    def download(self, item, log, progress=None):
        self.downloaded.append(item.title)
        if self._on_download:
            self._on_download(item)


class DownloadWorkerQueueTests(unittest.TestCase):
    def setUp(self):
        _install_pyside_stub()
        from tidal_dl.gui_app.workers import DownloadWorker

        self.DownloadWorker = DownloadWorker

    def test_worker_picks_up_items_added_during_run(self):
        first = SimpleNamespace(title="Album One")
        second = SimpleNamespace(title="Album Two")
        extra = []

        def on_download(item):
            if item.title == "Album One":
                extra.append(second)

        backend = RecordingBackend(on_download)
        worker = self.DownloadWorker(backend, [first])
        worker.more_items = lambda: list(extra)
        worker.run()

        self.assertEqual(backend.downloaded, ["Album One", "Album Two"])

    def test_worker_cancel_does_not_start_items_added_during_run(self):
        first = SimpleNamespace(title="Album One")
        second = SimpleNamespace(title="Album Two")
        extra = []
        worker_holder = {}

        def on_download(item):
            worker_holder["worker"].cancel()
            extra.append(second)

        backend = RecordingBackend(on_download)
        worker = self.DownloadWorker(backend, [first])
        worker.more_items = lambda: list(extra)
        worker_holder["worker"] = worker
        worker.run()

        self.assertEqual(backend.downloaded, ["Album One"])

    def test_worker_without_more_items_keeps_original_snapshot(self):
        first = SimpleNamespace(title="Album One")
        backend = RecordingBackend()
        worker = self.DownloadWorker(backend, [first])
        worker.run()
        self.assertEqual(backend.downloaded, ["Album One"])

    def test_worker_does_not_redownload_item_still_listed_as_queued(self):
        first = SimpleNamespace(title="Album One")
        backend = RecordingBackend()
        worker = self.DownloadWorker(backend, [first])
        worker.more_items = lambda: [first]
        worker.run()
        self.assertEqual(backend.downloaded, ["Album One"])

    def test_failure_details_precede_failed_status_and_hide_tokens(self):
        item = SimpleNamespace(title='Album')
        def fail(_):
            raise RuntimeError('Unavailable: access_token=dummy-secret')
        worker = self.DownloadWorker(RecordingBackend(fail), [item])
        events = []
        worker.signals.item_detail.connect(lambda _, detail: events.append(('detail', detail)))
        worker.signals.item_status.connect(lambda _, status: events.append(('status', status)))
        worker.run()
        self.assertEqual(events[-1], ('status', 'Failed'))
        self.assertEqual(events[-2][0], 'detail')
        self.assertIn('Unavailable', events[-2][1])
        self.assertNotIn('dummy-secret', events[-2][1])

    def test_partial_download_retains_deduplicated_warning_details(self):
        class WarningBackend:
            def download(self, item, log, progress):
                progress.note_warning('Cover could not be saved')
                progress.note_warning('Cover could not be saved')
        worker = self.DownloadWorker(WarningBackend(), [SimpleNamespace(title='Album')])
        details, statuses = [], []
        worker.signals.item_detail.connect(lambda _, detail: details.append(detail))
        worker.signals.item_status.connect(lambda _, status: statuses.append(status))
        worker.run()
        self.assertEqual(details, ['Cover could not be saved'])
        self.assertEqual(statuses[-1], 'Partial')

    def test_task_cancelled_before_start_does_not_run(self):
        from tidal_dl.gui_app.workers import TaskWorker
        calls, results, finished = [], [], []
        worker = TaskWorker(lambda: calls.append(True))
        worker.signals.result.connect(results.append)
        worker.signals.finished.connect(lambda: finished.append(True))
        worker.cancel()
        worker.run()
        self.assertEqual(calls, [])
        self.assertEqual(results, [])
        self.assertEqual(finished, [True])

    def test_task_cancelled_during_request_does_not_publish_late_result(self):
        from tidal_dl.gui_app.workers import TaskWorker
        results, errors, finished = [], [], []
        def query():
            worker.cancel()
            return 'Late response'
        worker = TaskWorker(query)
        worker.signals.result.connect(results.append)
        worker.signals.error.connect(errors.append)
        worker.signals.finished.connect(lambda: finished.append(True))
        worker.run()
        self.assertEqual(results, [])
        self.assertEqual(errors, [])
        self.assertEqual(finished, [True])


class CollectionRetryTests(unittest.TestCase):
    def setUp(self):
        _install_pyside_stub()
        from tidal_dl.gui_app.backend import SearchItem, TidekeeperBackend
        from tidal_dl.gui_app.workers import ItemProgressReporter
        from tidal_dl.enums import Type

        self.SearchItem = SearchItem
        self.TidekeeperBackend = TidekeeperBackend
        self.ItemProgressReporter = ItemProgressReporter
        self.Type = Type

    def test_artist_retry_uses_only_failed_media_after_queue_reload(self):
        from tidal_dl.gui_app import backend as gui_backend
        from tidal_dl.settings import SETTINGS

        with tempfile.TemporaryDirectory() as temp_dir, \
                mock.patch.object(SETTINGS, 'downloadPath', temp_dir), \
                mock.patch.object(gui_backend.PATHS, 'getConfigDirectory', return_value=temp_dir):
            backend = self.TidekeeperBackend()
            artist = self.SearchItem(self.Type.Artist, 'Artist', '', '', '42', '', SimpleNamespace(id=42))
            progress = self.ItemProgressReporter(artist, lambda *_: None)

            def start(kind, source, video_only=False, progress=None):
                self.assertEqual(kind, self.Type.Artist)
                progress.note_failed_track('123')
                progress.note_failed_video('456')
                return False

            with mock.patch.object(backend, '_ensure_catalog_session'), \
                    mock.patch.object(gui_backend, 'start_type', side_effect=start) as start_type:
                with self.assertRaisesRegex(RuntimeError, 'Download failed'):
                    backend.download(artist, progress=progress)
                self.assertEqual(start_type.call_count, 1)

                self.assertEqual(artist.failed_track_ids, ['123'])
                self.assertEqual(artist.failed_video_ids, ['456'])
                self.assertTrue(artist.retry_failed_media_only)

                artist.status = 'Failed'
                backend.save_queue([artist])
                retry_item, = backend.load_queue()
                self.assertEqual(retry_item.failed_track_ids, ['123'])
                self.assertTrue(retry_item.retry_failed_media_only)

                with mock.patch.object(gui_backend.TIDAL_API, 'getTypeData',
                                       side_effect=lambda identifier, kind: SimpleNamespace(id=identifier)), \
                        mock.patch.object(gui_backend, 'downloadTrack', return_value=(True, '')) as track, \
                        mock.patch.object(gui_backend, 'downloadVideo', return_value=(True, '')) as video:
                    backend.download(retry_item, progress=self.ItemProgressReporter(retry_item, lambda *_: None))

                self.assertEqual(start_type.call_count, 1)
                track.assert_called_once()
                self.assertEqual(track.call_args.args[0].id, '123')
                video.assert_called_once()
                self.assertIsNone(video.call_args.args[1])  # Artist videos keep their Video/ path.
                self.assertEqual(retry_item.failed_track_ids, [])
                self.assertEqual(retry_item.failed_video_ids, [])
                self.assertFalse(retry_item.retry_failed_media_only)

    def test_artist_failure_log_supplies_track_id_if_reporter_misses_it(self):
        from tidal_dl.gui_app import backend as gui_backend
        from tidal_dl.settings import SETTINGS

        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.object(SETTINGS, 'downloadPath', temp_dir):
            backend = self.TidekeeperBackend()
            artist = self.SearchItem(self.Type.Artist, 'Artist', '', '', '42', '', SimpleNamespace(id=42))
            log_path = Path(temp_dir) / 'failed-tracks.txt'
            log_path.write_text('https://tidal.com/browse/track/999\n', encoding='utf-8')

            def fail_artist(*_args, **_kwargs):
                with log_path.open('a', encoding='utf-8') as output:
                    output.write('# failed on this attempt\nhttps://tidal.com/browse/track/123\n')
                return False

            with mock.patch.object(backend, '_ensure_catalog_session'), \
                    mock.patch.object(gui_backend, 'start_type', side_effect=fail_artist):
                with self.assertRaisesRegex(RuntimeError, 'Download failed'):
                    backend.download(artist, progress=self.ItemProgressReporter(artist, lambda *_: None))

            self.assertEqual(artist.failed_track_ids, ['123'])
            self.assertTrue(artist.retry_failed_media_only)

    def test_legacy_artist_retry_filters_log_to_that_artist(self):
        from tidal_dl.gui_app import backend as gui_backend
        from tidal_dl.settings import SETTINGS

        with tempfile.TemporaryDirectory() as temp_dir, \
                mock.patch.object(SETTINGS, 'downloadPath', temp_dir), \
                mock.patch.object(SETTINGS, 'downloadVideos', True):
            (Path(temp_dir) / 'failed-tracks.txt').write_text(
                'https://tidal.com/browse/track/999\nhttps://tidal.com/browse/track/123\n', encoding='utf-8'
            )
            backend = self.TidekeeperBackend()
            artist = self.SearchItem(self.Type.Artist, 'Artist', '', '', '42', '', None, status='Queued')
            artist.legacy_retry_from_log = True
            with mock.patch.object(backend, '_ensure_catalog_session'), \
                    mock.patch.object(backend, 'artist_tracks', return_value=[SimpleNamespace(identifier='123')]), \
                    mock.patch.object(gui_backend.TIDAL_API, 'getTypeData',
                                      return_value=SimpleNamespace(id='123')), \
                    mock.patch.object(gui_backend, 'downloadTrack', return_value=(True, '')) as track, \
                    mock.patch.object(gui_backend, 'start_type') as start_type:
                backend.download(artist, progress=self.ItemProgressReporter(artist, lambda *_: None))
            track.assert_called_once()
            start_type.assert_not_called()
            self.assertEqual(artist.failed_track_ids, [])
            self.assertFalse(artist.retry_failed_media_only)

    def test_download_tracks_records_the_failed_id(self):
        from tidal_dl import download
        from tidal_dl.settings import SETTINGS

        tracks = [SimpleNamespace(id=1, title='Good'), SimpleNamespace(id=2, title='Failed')]
        reporter = self.ItemProgressReporter(SimpleNamespace(title='Album'), lambda *_: None)
        with mock.patch.object(SETTINGS, 'multiThread', False), \
                mock.patch.object(download, 'downloadTrack', side_effect=[(True, ''), (False, 'failed')]):
            success = download.downloadTracks(tracks, SimpleNamespace(id=10), progress=reporter)
        self.assertFalse(success)
        self.assertEqual(reporter.failed_track_ids, {'2'})

    def test_retry_keeps_only_ids_that_fail_again(self):
        from tidal_dl.gui_app import backend as gui_backend

        backend = self.TidekeeperBackend()
        artist = self.SearchItem(self.Type.Artist, 'Artist', '', '', '42', '', None,
                                 failed_track_ids=['1', '2'], retry_failed_media_only=True)
        attempted = []

        def download_track(source, *_args, **_kwargs):
            attempted.append(source.id)
            return (source.id == '1', '')

        with mock.patch.object(backend, '_ensure_catalog_session'), \
                mock.patch.object(gui_backend.TIDAL_API, 'getTypeData',
                                  side_effect=lambda identifier, kind: SimpleNamespace(id=identifier)), \
                mock.patch.object(gui_backend, 'downloadTrack', side_effect=download_track):
            with self.assertRaisesRegex(RuntimeError, 'Download failed'):
                backend.download(artist, progress=self.ItemProgressReporter(artist, lambda *_: None))
        self.assertEqual(attempted, ['1', '2'])
        self.assertEqual(artist.failed_track_ids, ['2'])
        self.assertTrue(artist.retry_failed_media_only)

    def test_album_retry_preserves_album_folder_after_queue_reload(self):
        from tidal_dl.gui_app import backend as gui_backend

        backend = self.TidekeeperBackend()
        item = self.SearchItem(self.Type.Album, 'Album', '', '', '77', '', None,
                               failed_track_ids=['1'], failed_video_ids=['2'], retry_failed_media_only=True)
        album = SimpleNamespace(id='77', title='Album')
        with mock.patch.object(backend, '_ensure_catalog_session'), \
                mock.patch.object(gui_backend.TIDAL_API, 'getTypeData',
                                  side_effect=lambda identifier, kind: SimpleNamespace(id=identifier)), \
                mock.patch.object(gui_backend.TIDAL_API, 'getAlbum', return_value=album) as get_album, \
                mock.patch.object(gui_backend, 'downloadTrack', return_value=(True, '')) as track, \
                mock.patch.object(gui_backend, 'downloadVideo', return_value=(True, '')) as video:
            backend.download(item, progress=self.ItemProgressReporter(item, lambda *_: None))
        get_album.assert_called_once_with('77')
        self.assertIs(track.call_args.args[1], album)
        self.assertIs(video.call_args.args[1], album)

if __name__ == "__main__":
    unittest.main()
