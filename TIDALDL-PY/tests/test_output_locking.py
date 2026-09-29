"""Coordination between writers to the same destination."""

import copy
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest import mock

from tidal_dl import download, runtime
from tidal_dl.enums import AudioQuality
from tidal_dl.model import StreamUrl, Track, Video, VideoStreamUrl
from tidal_dl.settings import SETTINGS

from fixtures import ApiFixture, response


def isolate_lock_directory(test, root):
    """Point every platform's lock folder into ``root``, for this process and children."""
    environment = mock.patch.dict(os.environ, {
        'HOME': str(root / 'home'), 'XDG_STATE_HOME': str(root / 'state'), 'LOCALAPPDATA': str(root / 'local'),
    })
    environment.start()
    test.addCleanup(environment.stop)


class DestinationLockIntegrationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        isolate_lock_directory(self, self.root / 'private')
        self.saved_settings = copy.deepcopy(SETTINGS.__dict__)
        def restore():
            SETTINGS.__dict__.clear()
            SETTINGS.__dict__.update(self.saved_settings)
        self.addCleanup(restore)
        SETTINGS.checkExist = True
        SETTINGS.showProgress = SETTINGS.showTrackInfo = SETTINGS.lyricFile = False
        SETTINGS.audioQuality = AudioQuality.High
        SETTINGS.downloadPath = str(self.root)

    def test_track_and_video_writers_hold_lock_through_completion_receipt(self):
        for kind in ('track', 'video'):
            with self.subTest(kind=kind):
                self._concurrent_downloads(kind)

    def _concurrent_downloads(self, kind):
        target = self.root / (kind + '.mp4')
        item = Track() if kind == 'track' else Video()
        item.id, item.title = 1, 'Test media'
        item.allowStreaming = True
        item.streamReady = True
        stream = StreamUrl() if kind == 'track' else VideoStreamUrl()
        stream.urls = ['https://cdn.example/segment']
        stream.url = stream.urls[0]
        stream.m3u8Url = 'https://cdn.example/playlist.m3u8'
        stream.codec, stream.container = 'aac', 'mp4'
        at_receipt, release_receipt, second_attempt = (threading.Event() for _ in range(3))
        errors, results = [], []
        original_receipt = download.record_completion

        @contextmanager
        def observe_lock(path):
            if threading.current_thread().name == 'second':
                second_attempt.set()
            with runtime.output_lock(path):
                yield

        def transfer(urls, path, *args, **kwargs):
            Path(path).write_bytes(b'complete generated fixture')
            return True, ''

        def finalize(source, path):
            os.replace(source, path)
            return path

        def receipt(*args, **kwargs):
            at_receipt.set()
            if not release_receipt.wait(5):
                raise RuntimeError('Timed out waiting to record completion')
            original_receipt(*args, **kwargs)

        def worker():
            try:
                with runtime.job_context(output=lambda text: None):
                    results.append(download.downloadTrack(item) if kind == 'track' else download.downloadVideo(item))
            except BaseException as error:
                errors.append(error)

        with ExitStack() as patches:
            for name, value in (
                ('output_lock', observe_lock), ('_downloadUrls', transfer),
                ('record_completion', receipt), ('_finalizeVideoFile', finalize),
                ('_getTrackStream', lambda *args: stream),
                ('getTrackPath', lambda *args: str(target)), ('getVideoPath', lambda *args: str(target)),
                ('_resolveTrackForAtmosDownload', lambda track, album: (track, album)),
                ('_encrypted', lambda stream, source, path: os.replace(source, path)),
                ('_exportFlacFromContainer', lambda path, stream: path),
                ('_verifyMediaQuality', lambda *args: {}), ('_setMetaData', lambda *args: None),
                ('_saveLyricsForTrack', lambda *args: ''),
            ):
                patches.enter_context(mock.patch.object(download, name, side_effect=value))
            transferred = download._downloadUrls
            patches.enter_context(mock.patch.object(download.TIDAL_API, 'getVideoStreamUrl', return_value=stream))
            patches.enter_context(mock.patch.object(download.TIDAL_API, 'getTrackContributors', return_value=None))
            patches.enter_context(mock.patch.object(download.Printf, 'video'))
            patches.enter_context(mock.patch.object(download, '_httpRequest', return_value=response(
                b'#EXTM3U\n#EXT-X-PLAYLIST-TYPE:VOD\n#EXTINF:1,\nsegment\n')))
            first = threading.Thread(target=worker, name='first')
            second = threading.Thread(target=worker, name='second')
            first.start()
            try:
                self.assertTrue(at_receipt.wait(5), str(results))
                second.start()
                self.assertTrue(second_attempt.wait(2))
                self.assertEqual(transferred.call_count, 1)
            finally:
                release_receipt.set()
                first.join(5)
                if second.ident is not None:
                    second.join(5)
            self.assertFalse(first.is_alive() or second.is_alive())
            self.assertFalse(errors, errors)
            self.assertEqual(results, [(True, ''), (True, '')])
            self.assertEqual(transferred.call_count, 1, 'second writer should reuse the first receipt')

    def test_process_lock_cancellation_crash_release_and_reentrancy(self):
        target = str(self.root / 'shared')
        ready = self.root / 'ready'
        code = '''
import sys
from pathlib import Path
from tidal_dl.settings import SETTINGS
from tidal_dl.runtime import output_lock
SETTINGS.downloadPath = sys.argv[3]
with output_lock(sys.argv[1]):
    Path(sys.argv[2]).touch()
    sys.stdin.read()
'''
        child_environment = dict(os.environ)
        child_environment['XDG_STATE_HOME'] = str(self.root / 'other-private-state')
        child = subprocess.Popen([sys.executable, '-c', code, target, str(ready), str(self.root)],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 env=child_environment)
        try:
            deadline = time.monotonic() + 10
            while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(ready.exists(), 'child did not acquire the lock')
            cancel = threading.Event()
            timer = threading.Timer(0.15, cancel.set)
            timer.start()
            try:
                with runtime.job_context(cancel=cancel), self.assertRaises(runtime.DownloadCancelled):
                    with runtime.output_lock(target):
                        self.fail('acquired a lock held by another process')
            finally:
                timer.cancel()
        finally:
            child.terminate()
            child.communicate(timeout=10)
        self.assertFalse(runtime._output_locks)

        with runtime.output_lock(target), runtime.output_lock(target), runtime.output_lock(str(self.root / 'SHARED')):
            self.assertTrue(runtime._output_locks)
        self.assertFalse(runtime._output_locks)

    def test_distinct_directories_keep_distinct_locks_outside_download_folders(self):
        first, second = self.root / 'Folder', self.root / 'folder'
        first.mkdir()
        second.mkdir(exist_ok=True)
        if os.path.samefile(first, second):
            self.skipTest('Filesystem does not distinguish directory case')
        with runtime.output_lock(str(first / 'track')), runtime.output_lock(str(second / 'track')):
            self.assertGreaterEqual(len(runtime._output_locks), 2)
            self.assertEqual(len(list(Path(runtime.lock_directory()).glob('*.lock'))), 2)
            self.assertFalse(list(first.rglob('*.lock')) + list(second.rglob('*.lock')))
        self.assertFalse(runtime._output_locks)

    def test_unwritable_home_state_falls_back_to_temporary_storage(self):
        temporary_locks = self.root / 'temporary-locks'

        def prepare(directory, mode):
            if directory == str(self.root / 'blocked-state'):
                return False
            Path(directory).mkdir(parents=True, exist_ok=True)
            return True

        with mock.patch.object(runtime, '_preferred_lock_directory',
                               return_value=str(self.root / 'blocked-state')), \
                mock.patch.object(runtime, '_temporary_lock_directory',
                                  return_value=str(temporary_locks)), \
                mock.patch.object(runtime, '_prepare_lock_directory', side_effect=prepare):
            with runtime.output_lock(str(self.root / 'track')):
                self.assertTrue(list(temporary_locks.glob('slot-*.lock')))

    def test_shared_root_fallback_uses_portable_key_and_shared_locking(self):
        target = str(self.root / 'Album' / 'track')
        shared = self.root / '.tidekeeper-locks'
        calls = []

        @contextmanager
        def observe(lock_path, announce_wait, optional=False, shared=False):
            calls.append((lock_path, optional, shared))
            yield True

        def prepare(directory, mode):
            return os.path.abspath(directory) == os.path.abspath(shared)

        with mock.patch.object(runtime, '_prepare_lock_directory', side_effect=prepare), \
                mock.patch.object(runtime, '_shared_key', return_value='Album/track') as shared_key, \
                mock.patch.object(runtime, '_cooperative_lock', side_effect=observe):
            with runtime.output_lock(target):
                pass
        shared_key.assert_called_with(target)
        self.assertEqual(calls, [(runtime._slot_path(str(shared), 'Album/track'), False, True)])

    def test_lock_files_are_bounded_slots_not_one_file_per_track(self):
        with mock.patch.object(runtime, 'LOCK_SLOT_COUNT', 4):
            for index in range(40):
                with runtime.output_lock(str(self.root / f'track-{index}')):
                    pass
        private = Path(runtime.lock_directory())
        self.assertLessEqual(len(list(private.glob('slot-*.lock'))), 4)
        self.assertFalse(list(private.glob('[0-9a-f]' * 64 + '.lock')))

    def test_inactive_legacy_album_locks_are_cleaned_when_revisited(self):
        SETTINGS.downloadPath = str(self.root / 'other-download-root')
        album = self.root / 'Album'
        old_directory = album / '.tidekeeper-locks'
        old_directory.mkdir(parents=True)
        old_lock = old_directory / ('a' * 64 + '.lock')
        old_lock.touch()
        stale = time.time() - runtime.LEGACY_LOCK_GRACE_SECONDS - 1
        os.utime(old_lock, (stale, stale))
        with runtime.output_lock(str(album / 'track')):
            pass
        self.assertFalse(old_directory.exists())

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Termux runs on Linux')
    def test_termux_locks_live_in_private_home_and_distinguish_destinations(self):
        private_home = self.root / 'private-home'
        private_home.mkdir()
        first, second = self.root / 'shared' / 'album-1', self.root / 'shared' / 'album-2'
        first.mkdir(parents=True)
        second.mkdir(parents=True)
        with mock.patch.dict(os.environ, {'TERMUX_VERSION': 'test', 'HOME': str(private_home)}):
            os.environ.pop('XDG_STATE_HOME', None)
            with runtime.output_lock(str(first / 'track')), runtime.output_lock(str(second / 'track')):
                locks = list((private_home / '.local' / 'state' / 'tidekeeper' / 'locks').glob('*.lock'))
                self.assertEqual(len(locks), 2)
                self.assertGreaterEqual(len(runtime._output_locks), 2)
                self.assertFalse(list((self.root / 'shared').rglob('*.lock')))
        self.assertFalse(runtime._output_locks)


class OutputLockTests(ApiFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        isolate_lock_directory(self, self.root / 'private')

    def test_output_lock_wait_is_cancellable_and_cleans_up(self):
        cancel = threading.Event()
        finished = threading.Event()
        outcomes = []
        target = str(self.root / 'audio')

        def writer():
            try:
                with runtime.job_context(cancel=cancel), runtime.output_lock(target):
                    outcomes.append('acquired')
            except runtime.DownloadCancelled:
                outcomes.append('cancelled')
            finally:
                finished.set()

        with runtime.output_lock(target):
            thread = threading.Thread(target=writer)
            thread.start()
            try:
                self.assertFalse(finished.wait(0.05))
                cancel.set()
                self.assertTrue(finished.wait(2))
            finally:
                cancel.set()
                thread.join(timeout=2)
        self.assertEqual(outcomes, ['cancelled'])
        self.assertFalse(runtime._output_locks)

    def test_waiting_for_another_writer_is_announced_once(self):
        target = str(self.root / 'Artist - Song')
        messages, acquired = [], threading.Event()

        def writer():
            with runtime.job_context(output=messages.append), runtime.output_lock(target):
                acquired.set()

        with mock.patch.object(runtime, 'LOCK_NOTICE_SECONDS', 0.05):
            with runtime.output_lock(target):
                thread = threading.Thread(target=writer)
                thread.start()
                self.assertFalse(acquired.wait(0.4))
            self.assertTrue(acquired.wait(2))
            thread.join(timeout=2)
        self.assertEqual(len(messages), 1)
        self.assertIn('Waiting for another download to finish writing "Artist - Song"', messages[0])


if __name__ == "__main__":
    unittest.main()
