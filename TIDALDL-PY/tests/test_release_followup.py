"""Behavioral regressions for the 2026.9.26 release follow-up."""
import copy
from contextlib import contextmanager, ExitStack
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

import requests

import tidal_dl
from tidal_dl import download, events, manifests, runtime
from tidal_dl.enums import AudioQuality, Type
from tidal_dl.model import StreamUrl, Track, Video, VideoStreamUrl
from tidal_dl.settings import SETTINGS
from tidal_dl.tidal import TidalAPI


def response(content=b'', status=200, headers=None):
    result = requests.Response()
    result.status_code = status
    result._content = content
    result._content_consumed = True
    result.headers.update(headers or {})
    result.url = 'https://cdn.example/playlist.m3u8'
    result.close = mock.Mock()
    return result


class ReleaseFollowupTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        saved = copy.deepcopy(SETTINGS.__dict__)
        def restore():
            SETTINGS.__dict__.clear()
            SETTINGS.__dict__.update(saved)
        self.addCleanup(restore)
        SETTINGS.downloadPath = str(self.root)
        self.api = TidalAPI()
        self.addCleanup(self.api.session.close)

    def test_schemeless_links_keep_strict_host_and_id_validation(self):
        for link, expected in (
            ('tidal.com/browse/album/123', (Type.Album, '123')),
            ('listen.tidal.com/track/1', (Type.Track, '1')),
            ('WWW.TIDAL.COM/browse/video/42', (Type.Video, '42')),
            ('tidal.com:443/browse/playlist/abc-123?source=share', (Type.Playlist, 'abc-123')),
        ):
            with self.subTest(link=link):
                self.assertEqual(self.api.parseUrl(link), expected)
        for link in ('tidal.com.example/track/1', 'tidal.com@other.example/track/1',
                     'not-tidal.com/track/1', 'tidal.com/track/not-a-number',
                     'tidal.com:81/track/1', '//other.example/track/1'):
            with self.subTest(link=link):
                self.assertEqual(self.api.parseUrl(link)[0], Type.Null)

    def test_cli_link_and_batch_resolve_schemeless_catalog_links(self):
        batch = self.root / 'links.txt'
        batch.write_text('tidal.com/browse/album/123\nlisten.tidal.com/track/1\n')
        for argument, expected in (
            ('tidal.com/browse/album/123', [('123', Type.Album)]),
            (str(batch), [('123', Type.Album), ('1', Type.Track)]),
        ):
            with self.subTest(argument=argument), \
                    mock.patch('sys.argv', ['tidekeeper', '--link', argument]), \
                    mock.patch.object(tidal_dl, 'loginByConfig', return_value=True), \
                    mock.patch.object(events, 'TIDAL_API', self.api), \
                    mock.patch.object(self.api, 'getTypeData', return_value=object()) as lookup, \
                    mock.patch.object(events, 'start_type', return_value=True), \
                    runtime.job_context(output=lambda text: None):
                self.assertEqual(tidal_dl.mainCommand(), 0)
                self.assertEqual([call.args for call in lookup.call_args_list], expected)

    def test_cancel_device_login_does_not_invalidate_a_token_refresh(self):
        self.api.key.accessToken = 'saved-access'
        original_generation = self.api._sessionGeneration
        grant = {'user': {'userId': 'test-user', 'countryCode': 'US'},
                 'access_token': 'renewed-access', 'refresh_token': 'renewed-refresh', 'expires_in': 60}
        def refresh(*args):
            self.api.cancelDeviceLogin()
            return grant
        with mock.patch.object(self.api, '__post__', side_effect=refresh):
            self.assertTrue(self.api.refreshAccessToken('saved-refresh'))
        self.assertEqual(self.api.key.accessToken, 'renewed-access')
        self.assertEqual(self.api._sessionGeneration, original_generation)

    def test_cancel_device_login_preserves_search_and_playback_session(self):
        self.api.key.accessToken = 'saved-access'
        old_key = self.api.__streamCacheKey__('1', [AudioQuality.High])
        def search(*args, **kwargs):
            self.api.cancelDeviceLogin()
            return response(json.dumps({'tracks': {'items': []}}).encode())
        with mock.patch.object(self.api.session, 'get', side_effect=search):
            self.assertEqual(self.api.__getOnce__('search'), {'tracks': {'items': []}})
        self.assertEqual(self.api.key.accessToken, 'saved-access')
        self.assertEqual(self.api.__streamCacheKey__('1', [AudioQuality.High]), old_key)

    def test_cancelled_device_grant_cannot_replace_saved_login(self):
        self.api.key.accessToken = 'saved-access'
        def late_grant(*args):
            self.api.cancelDeviceLogin()
            return {'user': {'userId': 'late-user', 'countryCode': 'US'},
                    'access_token': 'late-access', 'refresh_token': 'late-refresh', 'expires_in': 60}
        with mock.patch.object(self.api, '__post__', side_effect=late_grant):
            self.assertFalse(self.api.checkAuthStatus())
        self.assertEqual(self.api.key.accessToken, 'saved-access')

    def test_cancelled_device_request_cannot_install_challenge_or_backoff(self):
        for result, method in (
            ({'deviceCode': 'device', 'userCode': 'code', 'verificationUri': 'link.tidal.com',
              'expiresIn': 60, 'interval': 5}, self.api.getDeviceCode),
            ({'error': 'slow_down'}, self.api.checkAuthStatus),
        ):
            def cancel(*args):
                self.api.cancelDeviceLogin()
                return result
            self.api.key.authCheckInterval = 5
            with mock.patch.object(self.api, '__post__', side_effect=cancel):
                if method == self.api.getDeviceCode:
                    with self.assertRaisesRegex(Exception, 'cancelled'):
                        method()
                else:
                    self.assertFalse(method())
            self.assertIsNone(self.api.key.deviceCode)
            self.assertEqual(self.api.key.authCheckInterval, 5)

    def test_vod_without_end_marker_is_complete_but_event_is_not(self):
        for kind in ('VOD', 'EVENT', ''):
            content = f'#EXTM3U\n#EXT-X-PLAYLIST-TYPE:{kind}\n#EXTINF:1,\none.ts\n'
            if kind == 'VOD':
                self.assertEqual(manifests.hls_segments(content, 'https://cdn.example/index.m3u8'),
                                 ['https://cdn.example/one.ts'])
            else:
                with self.assertRaisesRegex(ValueError, 'Live or unfinished'):
                    manifests.hls_segments(content, 'https://cdn.example/index.m3u8')

    def test_encoded_response_preserves_resume_file_and_closes_response(self):
        target = self.root / 'audio.part'
        partial = Path(str(target) + '.download')
        partial.write_bytes(b'valid-prefix')
        result = response(b'unused', headers={'Content-Encoding': 'gzip'})
        result.iter_content = mock.Mock()
        with mock.patch.object(download, '__httpRequest__', return_value=result) as request:
            with self.assertRaisesRegex(ValueError, 'encoded response'):
                download.__downloadSingleUrl__('https://cdn.example/audio', str(target))
        self.assertEqual(partial.read_bytes(), b'valid-prefix')
        result.iter_content.assert_not_called()
        result.close.assert_called_once()
        self.assertEqual(request.call_args.kwargs['headers'],
                         {'Accept-Encoding': 'identity', 'Range': 'bytes=12-'})

    def test_unexpected_initial_range_is_rejected_before_body_write(self):
        target = self.root / 'audio.part'
        result = response(b'unused', status=206, headers={'Content-Range': 'bytes 4-9/10'})
        result.iter_content = mock.Mock()
        with mock.patch.object(download, '__httpRequest__', return_value=result):
            with self.assertRaisesRegex(ValueError, 'unexpected byte range'):
                download.__downloadSingleUrl__('https://cdn.example/audio', str(target))
        result.iter_content.assert_not_called()
        result.close.assert_called_once()
        self.assertFalse(target.exists())
        self.assertFalse(Path(str(target) + '.download').exists())

    def test_https_redirect_downgrade_is_rejected_without_second_request(self):
        result = response(status=302, headers={'Location': 'http://cdn.example/audio'})
        session = mock.Mock()
        session.request.return_value = result
        with mock.patch.object(download, '__httpSession__', return_value=session), \
                mock.patch.object(download, 'validate_media_url'):
            with self.assertRaisesRegex(ValueError, 'downgrade'):
                download.__httpRequest__('GET', 'https://cdn.example/audio', allow_redirects=True)
        session.request.assert_called_once()
        result.close.assert_called_once()

    def test_https_redirect_still_downloads_and_closes_each_response(self):
        first = response(status=302, headers={'Location': 'https://cdn.example/final'})
        second = response(b'audio', headers={'Content-Length': '5'})
        session = mock.Mock()
        session.request.side_effect = [first, second]
        with mock.patch.object(download, '__httpSession__', return_value=session), \
                mock.patch.object(download, 'validate_media_url'):
            target = self.root / 'audio'
            self.assertEqual(download.__downloadSingleUrl__('https://cdn.example/audio', str(target)), 5)
        self.assertEqual(target.read_bytes(), b'audio')
        first.close.assert_called_once()
        second.close.assert_called_once()
        self.assertEqual(session.request.call_count, 2)


class DestinationLockIntegrationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.saved_settings = copy.deepcopy(SETTINGS.__dict__)
        def restore():
            SETTINGS.__dict__.clear()
            SETTINGS.__dict__.update(self.saved_settings)
        self.addCleanup(restore)
        SETTINGS.checkExist = True
        SETTINGS.showProgress = SETTINGS.showTrackInfo = SETTINGS.lyricFile = False
        SETTINGS.audioQuality = AudioQuality.High

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
                ('output_lock', observe_lock), ('__downloadUrls__', transfer),
                ('record_completion', receipt), ('__finalizeVideoFile__', finalize),
                ('__getTrackStream__', lambda *args: stream),
                ('getTrackPath', lambda *args: str(target)), ('getVideoPath', lambda *args: str(target)),
                ('__resolveTrackForAtmosDownload__', lambda track, album: (track, album)),
                ('__encrypted__', lambda stream, source, path: os.replace(source, path)),
                ('__exportFlacFromContainer__', lambda path, stream: path),
                ('__verifyMediaQuality__', lambda *args: {}), ('__setMetaData__', lambda *args: None),
                ('__saveLyricsForTrack__', lambda *args: ''),
            ):
                patches.enter_context(mock.patch.object(download, name, side_effect=value))
            transferred = download.__downloadUrls__
            patches.enter_context(mock.patch.object(download.TIDAL_API, 'getVideoStreamUrl', return_value=stream))
            patches.enter_context(mock.patch.object(download.TIDAL_API, 'getTrackContributors', return_value=None))
            patches.enter_context(mock.patch.object(download.Printf, 'video'))
            patches.enter_context(mock.patch.object(download, '__httpRequest__', return_value=response(
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
from tidal_dl.runtime import output_lock
with output_lock(sys.argv[1]):
    Path(sys.argv[2]).touch()
    sys.stdin.read()
'''
        child = subprocess.Popen([sys.executable, '-c', code, target, str(ready)],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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

    def test_distinct_directories_keep_distinct_os_locks(self):
        first, second = self.root / 'Folder', self.root / 'folder'
        first.mkdir()
        second.mkdir(exist_ok=True)
        if os.path.samefile(first, second):
            self.skipTest('Filesystem does not distinguish directory case')
        with runtime.output_lock(str(first / 'track')), runtime.output_lock(str(second / 'track')):
            self.assertEqual(len(runtime._output_locks), 2)
            self.assertEqual(len(list(first.rglob('*.lock'))), 1)
            self.assertEqual(len(list(second.rglob('*.lock'))), 1)
        self.assertFalse(runtime._output_locks)


if __name__ == '__main__':
    unittest.main()
