import json
import sys
import tempfile
import unittest
from contextlib import ExitStack
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
                progress.note_failed_video('456', '77')
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
                self.assertEqual(retry_item.failed_video_album_ids, {'456': ['77']})
                self.assertTrue(retry_item.retry_failed_media_only)

                with mock.patch.object(gui_backend.TIDAL_API, 'getTypeData',
                                       side_effect=lambda identifier, kind: SimpleNamespace(id=identifier)), \
                        mock.patch.object(gui_backend.TIDAL_API, 'getAlbum',
                                          return_value=SimpleNamespace(id='77')) as get_album, \
                        mock.patch.object(gui_backend, 'downloadTrack', return_value=(True, '')) as track, \
                        mock.patch.object(gui_backend, 'downloadVideo', return_value=(True, '')) as video:
                    backend.download(retry_item, progress=self.ItemProgressReporter(retry_item, lambda *_: None))

                self.assertEqual(start_type.call_count, 1)
                track.assert_called_once()
                self.assertEqual(track.call_args.args[0].id, '123')
                video.assert_called_once()
                self.assertIs(video.call_args.args[1], get_album.return_value)
                self.assertEqual(retry_item.failed_track_ids, [])
                self.assertEqual(retry_item.failed_video_ids, [])
                self.assertEqual(retry_item.failed_video_album_ids, {})
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

    def test_artist_without_retry_details_revisits_collection_despite_failure_log(self):
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
            with mock.patch.object(backend, '_ensure_catalog_session'), \
                    mock.patch.object(gui_backend.TIDAL_API, 'getTypeData',
                                      return_value=SimpleNamespace(id='42')) as get_artist, \
                    mock.patch.object(gui_backend, 'start_type', return_value=True) as start_type:
                backend.download(artist, progress=self.ItemProgressReporter(artist, lambda *_: None))
            self.assertEqual(start_type.call_args.args[:2], (self.Type.Artist, get_artist.return_value))
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

class CollectionRetryFlowTests(unittest.TestCase):
    """Exercise collection traversal and saved retries with catalog/transfer IO stubbed."""

    def setUp(self):
        _install_pyside_stub()
        from tidal_dl import download, events
        from tidal_dl.enums import AudioQuality, Type
        from tidal_dl.gui_app import backend
        from tidal_dl.model import Album, Artist, Track, Video
        from tidal_dl.settings import SETTINGS

        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.gui, self.download, self.Type = backend, download, Type
        self.backend = backend.TidekeeperBackend()
        self.artist = self.model(Artist, id='42', name='Artist')
        self.albums = [self.model(Album, id=identifier, title='Album ' + identifier,
                                 artist=self.artist, artists=[self.artist]) for identifier in ('77', '88')]
        self.tracks = [self.model(Track, id=identifier, title='Track ' + identifier, album=album,
                                 artist=self.artist, artists=[self.artist])
                       for identifier, album in zip(('123', '789'), self.albums)]
        self.video = self.model(Video, id='456', title='Video', album=self.albums[0],
                                artist=self.artist, artists=[self.artist])
        self.contents = {'77': ([self.tracks[0]], [self.video]), '88': ([self.tracks[1]], [])}
        self.item = backend.SearchItem(Type.Artist, 'Artist', '', '', '42', '', self.artist)
        self.track_results, self.video_results = {}, {}
        self.track_attempts, self.video_attempts = [], []
        self.catalog_error = None
        for key, value in dict(downloadPath=str(self.root), multiThread=False,
                               downloadVideos=True, saveAlbumInfo=False, saveCovers=False,
                               audioQuality=AudioQuality.HiFi, audioQualityPriority=[]).items():
            self.patch(SETTINGS, key, value)
        self.patch(self.backend, '_ensure_catalog_session')
        self.patch(backend.PATHS, 'getConfigDirectory', return_value=str(self.root))
        self.patch(events.Printf, 'album')
        self.patch(events.Printf, 'artist')
        self.patch(backend.TIDAL_API, 'getArtistAlbums', return_value=self.albums)
        self.patch(backend.TIDAL_API, 'getArtistVideos', return_value=[self.video])
        self.patch(backend.TIDAL_API, 'getItems', side_effect=self.get_items)
        self.patch(backend.TIDAL_API, 'getAlbum', side_effect=lambda identifier: next(
            album for album in self.albums if album.id == str(identifier)))
        self.patch(backend.TIDAL_API, 'getTypeData', side_effect=self.get_type_data)
        for module in (download, backend):
            self.patch(module, 'downloadTrack', side_effect=self.download_track)
            self.patch(module, 'downloadVideo', side_effect=self.download_video)

    @staticmethod
    def model(cls, **values):
        obj = cls()
        for key, value in values.items():
            setattr(obj, key, value)
        return obj

    def patch(self, *args, **kwargs):
        return self.stack.enter_context(mock.patch.object(*args, **kwargs))

    def get_items(self, identifier, kind):
        if identifier == self.catalog_error:
            raise RuntimeError('Temporary catalog failure')
        return self.contents[identifier]

    def get_type_data(self, identifier, kind):
        if kind == self.Type.Artist:
            return self.artist
        if kind == self.Type.Video:
            return self.video
        return next(obj for obj in self.tracks + self.albums if obj.id == identifier)

    def download_track(self, track, album=None, *args, **kwargs):
        self.track_attempts.append(track.id)
        ok = self.track_results.get(track.id, True)
        if not ok:
            self.download.__logFailedTrack__(track, album, reason='Transfer failed')
        return ok, ''

    def download_video(self, video, album=None, *args, **kwargs):
        from tidal_dl.paths import getVideoPath
        album_id = getattr(album, 'id', None)
        self.video_attempts.append((video.id, album_id, getVideoPath(video, album)))
        return self.video_results.get((video.id, album_id), True), ''

    def run_download(self):
        from tidal_dl.gui_app.workers import DownloadWorker
        worker = DownloadWorker(self.backend, [self.item])
        worker.signals = mock.Mock()
        worker.signals.item_status.emit.side_effect = lambda item, status: setattr(item, 'status', status)
        worker.run()

    def reload_queue(self, legacy=False, missing_video_context=False):
        self.backend.save_queue([self.item])
        path = self.root / '.tidekeeper-queue.json'
        rows = json.loads(path.read_text())
        if legacy:
            for field in ('failed_track_ids', 'failed_video_ids', 'failed_video_album_ids', 'retry_failed_media_only'):
                rows[0].pop(field)
        elif missing_video_context:
            rows[0].pop('failed_video_album_ids')
        path.write_text(json.dumps(rows))
        self.item, = self.backend.load_queue()

    def test_retry_after_catalog_exception_includes_unattempted_album(self):
        self.track_results['123'] = False
        self.catalog_error = '88'
        self.run_download()
        self.assertEqual(self.item.status, 'Failed')
        self.assertEqual(self.track_attempts, ['123'])
        self.assertFalse(self.item.retry_failed_media_only)
        self.reload_queue()
        self.catalog_error = None
        self.track_results.clear()
        self.run_download()
        self.assertEqual(self.track_attempts, ['123', '123', '789'])
        self.assertEqual(self.item.status, 'Done')

    def test_legacy_queue_retries_failed_tracks_and_videos(self):
        for kind in (self.Type.Artist, self.Type.Album):
            with self.subTest(kind=kind):
                source = self.artist if kind == self.Type.Artist else self.albums[0]
                self.item = self.gui.SearchItem(kind, source.title if kind == self.Type.Album else source.name,
                                                '', '', source.id, '', source)
                self.track_results['123'] = False
                self.video_results[('456', '77')] = False
                self.run_download()
                self.assertEqual(self.item.status, 'Failed')
                self.reload_queue(legacy=True)
                self.track_results.clear()
                self.video_results.clear()
                self.track_attempts.clear()
                self.video_attempts.clear()
                self.run_download()
                self.assertIn('123', self.track_attempts)
                self.assertEqual([attempt[:2] for attempt in self.video_attempts], [('456', '77')])
                self.assertEqual(self.item.status, 'Done')

    def test_artist_video_retry_preserves_album_path_after_restart(self):
        self.video_results[('456', '77')] = False
        self.run_download()
        self.assertEqual(self.item.failed_video_album_ids, {'456': ['77']})
        original_path = self.video_attempts[0][2]
        self.reload_queue()
        # The standalone video endpoint need not include its containing album.
        self.video.album = None
        self.video_results.clear()
        self.track_attempts.clear()
        self.run_download()
        self.assertEqual(self.item.status, 'Done')
        self.assertEqual(self.video_attempts[-1][2], original_path)
        self.assertEqual(self.track_attempts, [])
        self.assertEqual(self.item.failed_video_album_ids, {})

    def test_artist_video_only_retry_keeps_video_folder(self):
        self.item.video_only = True
        self.video_results[('456', None)] = False
        self.run_download()
        original_path = self.video_attempts[0][2]
        self.assertIn('/Video/', original_path)
        self.reload_queue()
        self.video_results.clear()
        self.run_download()
        self.assertEqual(self.video_attempts[-1][2], original_path)
        self.assertEqual(self.item.status, 'Done')

    def test_artist_video_without_saved_album_context_revisits_collection(self):
        self.video_results[('456', '77')] = False
        self.run_download()
        self.reload_queue(missing_video_context=True)
        self.video.album = None
        self.video_results.clear()
        self.run_download()
        self.assertEqual(self.video_attempts[0], self.video_attempts[-1])
        self.assertEqual(self.item.status, 'Done')

    def test_shared_video_retains_only_album_contexts_that_still_fail(self):
        self.contents['88'][1].append(self.video)
        self.video_results.update({('456', '77'): False, ('456', '88'): False})
        self.run_download()
        self.reload_queue()
        self.assertEqual(self.item.failed_video_album_ids, {'456': ['77', '88']})
        self.video_results[('456', '77')] = True
        self.run_download()
        self.assertEqual(self.item.status, 'Failed')
        self.assertEqual(self.item.failed_video_album_ids, {'456': ['88']})
        self.reload_queue()
        self.video_results.clear()
        self.video_attempts.clear()
        self.run_download()
        self.assertEqual([attempt[:2] for attempt in self.video_attempts], [('456', '88')])
        self.assertEqual(self.item.status, 'Done')

    def test_session_error_preserves_targeted_retry_across_restart(self):
        self.track_results['123'] = False
        self.run_download()
        with mock.patch.object(self.backend, '_ensure_catalog_session', side_effect=RuntimeError('Sign in again')):
            self.run_download()
        self.assertTrue(self.item.retry_failed_media_only)
        self.reload_queue()
        self.track_results.clear()
        self.track_attempts.clear()
        self.run_download()
        self.assertEqual(self.track_attempts, ['123'])
        self.assertEqual(self.item.status, 'Done')

    def test_cancellation_keeps_all_pending_video_contexts(self):
        from tidal_dl.runtime import DownloadCancelled
        self.contents['88'][1].append(self.video)
        self.video_results.update({('456', '77'): False, ('456', '88'): False})
        self.run_download()
        with mock.patch.object(self.gui, 'downloadVideo', side_effect=[(True, ''), DownloadCancelled()]):
            self.run_download()
        self.assertEqual(self.item.status, 'Cancelled')
        self.reload_queue()
        self.assertTrue(self.item.retry_failed_media_only)
        self.assertEqual(self.item.failed_video_album_ids, {'456': ['77', '88']})
        self.video_results.clear()
        self.run_download()
        self.assertEqual(self.item.status, 'Done')


if __name__ == "__main__":
    unittest.main()
