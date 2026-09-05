import copy
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

import requests

import tidal_dl
from tidal_dl import download, events
from tidal_dl.enums import AudioQuality, Type, VideoQuality
from tidal_dl.gui_app.backend import SearchItem, TidekeeperBackend, queue_item
from tidal_dl.manifests import dash_segments, hls_segments, hls_variants
from tidal_dl.paths import PATHS
from tidal_dl.runtime import DownloadCancelled, job_context, redact, run_process
from tidal_dl.settings import SETTINGS, TOKEN, Settings
from tidal_dl.tidal import TIDAL_API, TidalAPI, TidalApiError
from tidal_dl.transfer_state import audio_identity, is_completed, prepare_transfer, record_completion, video_identity


class Response:
    def __init__(self, content=b'', status=200, headers=None, body=None):
        self.content = content
        self.status_code = status
        self.headers = headers or {'Content-Length': str(len(content))}
        self.body = body
        self.closed = False

    def json(self):
        return self.body

    @property
    def text(self):
        if self.body is not None:
            return json.dumps(self.body)
        if isinstance(self.content, bytes):
            return self.content.decode('utf-8', 'replace')
        return '' if self.content is None else str(self.content)

    def iter_content(self, chunk_size):
        yield self.content

    def close(self):
        self.closed = True

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code), response=self)


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = copy.deepcopy(SETTINGS.__dict__)
        self.addCleanup(self.restore_settings)

    def restore_settings(self):
        SETTINGS.__dict__.clear()
        SETTINGS.__dict__.update(self.settings)

    def test_changed_stream_discards_numbered_segments(self):
        path = str(self.root / 'video.part')
        prepare_transfer(path, ['https://cdn.invalid/old0', 'https://cdn.invalid/old1'])
        parts = Path(path + '.parts')
        parts.mkdir()
        (parts / '000000.part').write_bytes(b'OLD')
        Path(path).write_bytes(b'OLD-STREAM')
        with mock.patch.object(download, '__httpRequest__', side_effect=[Response(b'NEW'), Response(b'DATA')]):
            ok, message = download.__downloadUrls__(['https://cdn.invalid/new0', 'https://cdn.invalid/new1'],
                                                   path, threadNum=1, probeSize=False)
        self.assertTrue(ok, message)
        self.assertEqual(Path(path).read_bytes(), b'NEWDATA')

    def test_signed_urls_are_hashed_on_disk(self):
        path = str(self.root / 'part')
        prepare_transfer(path, ['https://cdn.invalid/file?signature=dummy-secret'])
        self.assertNotIn('dummy-secret', Path(path + '.source.json').read_text())

    def test_matching_416_promotes_complete_partial(self):
        path = str(self.root / 'part')
        urls = ['https://cdn.invalid/file']
        prepare_transfer(path, urls)
        Path(path + '.download').write_bytes(b'complete')
        response = Response(status=416, headers={'Content-Range': 'bytes */8'})
        error = requests.HTTPError('416', response=response)
        with mock.patch.object(download, '__httpRequest__', side_effect=error):
            ok, message = download.__downloadUrls__(urls, path, probeSize=False, expectedSize=8)
        self.assertTrue(ok, message)
        self.assertEqual(Path(path).read_bytes(), b'complete')

    def test_overlong_416_restarts_transfer(self):
        path = str(self.root / 'part')
        urls = ['https://cdn.invalid/file']
        prepare_transfer(path, urls)
        Path(path + '.download').write_bytes(b'overlong-data')
        error = requests.HTTPError('416', response=Response(status=416, headers={'Content-Range': 'bytes */3'}))
        with mock.patch.object(download, '__httpRequest__', side_effect=[error, Response(b'new')]):
            ok, message = download.__downloadUrls__(urls, path, probeSize=False, expectedSize=3)
        self.assertTrue(ok, message)
        self.assertEqual(Path(path).read_bytes(), b'new')

    def test_truncated_flac_is_not_skipped(self):
        SETTINGS.checkExist = SETTINGS.saveAsFlac = True
        path = str(self.root / 'track.flac')
        Path(path).write_bytes(b'fLaC' + b'\0' * 2048)
        stream = SimpleNamespace(trackid=1, soundQuality='LOSSLESS', codec='flac', container='mp4')
        self.assertIsNone(download.__skipPath__(path, stream))

    def test_receipt_rejects_tampering_and_different_quality(self):
        path = str(self.root / 'track.flac')
        Path(path).write_bytes(b'media')
        identity = {'type': 'track', 'id': '1', 'quality': 'LOSSLESS'}
        record_completion(path, identity)
        self.assertTrue(is_completed(path, identity))
        self.assertFalse(is_completed(path, dict(identity, quality='HIGH')))
        Path(path).write_bytes(b'other')
        self.assertFalse(is_completed(path, identity))

    def test_video_skip_requires_verified_completion(self):
        path = str(self.root / 'video.mp4')
        video = SimpleNamespace(id=2, title='Video')
        SETTINGS.checkExist = True
        SETTINGS.videoQuality = VideoQuality.P720
        Path(path).write_bytes(b'video')
        record_completion(path, video_identity(video, SETTINGS.videoQuality))
        with mock.patch.object(download, 'getVideoPath', return_value=path), \
             mock.patch.object(TIDAL_API, 'getVideoStreamUrl') as resolve:
            self.assertEqual(download.downloadVideo(video, None), (True, ''))
        resolve.assert_not_called()

    def test_video_remux_failure_preserves_both_files(self):
        part, final = self.root / 'video.part', self.root / 'video.mp4'
        part.write_bytes(b'transport-stream')
        final.write_bytes(b'previous-good-video')
        with mock.patch.object(download.shutil, 'which', return_value='ffmpeg'), \
             mock.patch.object(download.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stderr=b'bad stream')):
            with self.assertRaisesRegex(RuntimeError, 'Video conversion failed'):
                download.__finalizeVideoFile__(str(part), str(final))
        self.assertEqual(part.read_bytes(), b'transport-stream')
        self.assertEqual(final.read_bytes(), b'previous-good-video')

    def test_missing_ffmpeg_does_not_create_fake_mp4(self):
        part, final = self.root / 'video.part', self.root / 'video.mp4'
        part.write_bytes(b'transport-stream')
        with mock.patch.object(download.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'ffmpeg'):
                download.__finalizeVideoFile__(str(part), str(final))
        self.assertTrue(part.exists())
        self.assertFalse(final.exists())

    def test_cancel_during_transfer_keeps_partial_and_existing_output(self):
        path = str(self.root / 'track')
        Path(path).write_bytes(b'previous-good')
        cancelled = threading.Event()
        class Interrupted(Response):
            def iter_content(self, chunk_size):
                yield b'first'
                cancelled.set()
                yield b'second'
        with job_context(cancel=cancelled), mock.patch.object(download, '__httpRequest__', return_value=Interrupted()):
            with self.assertRaises(DownloadCancelled):
                download.__downloadUrls__(['https://cdn.invalid/file'], path, probeSize=False)
        self.assertEqual(Path(path).read_bytes(), b'previous-good')
        self.assertEqual(Path(path + '.download').read_bytes(), b'first')

    def test_media_process_is_stopped_on_cancellation(self):
        cancelled = threading.Event()
        timer = threading.Timer(0.1, cancelled.set)
        timer.start()
        try:
            with job_context(cancel=cancelled), self.assertRaises(DownloadCancelled):
                run_process([sys.executable, '-c', 'import time; time.sleep(30)'], timeout=3)
        finally:
            timer.cancel()

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

    def test_config_override_equals_and_space_forms(self):
        old = PATHS.homePathOverride
        self.addCleanup(setattr, PATHS, 'homePathOverride', old)
        for args in [['--configPathOverride=' + str(self.root)], ['--configPathOverride', str(self.root)],
                     ['-c', str(self.root)], ['-c' + str(self.root)]]:
            with self.subTest(args=args), mock.patch.object(sys, 'argv', ['tidekeeper', *args, '--help']):
                tidal_dl.preMainCommand()
                self.assertEqual(PATHS.homePathOverride, str(self.root))

    def test_hls_relative_segments_and_initialization(self):
        content = '#EXTM3U\n#EXT-X-MAP:URI="init.mp4"\n../one.m4s\ntwo.m4s\n'
        self.assertEqual(hls_segments(content, 'https://cdn.invalid/video/index.m3u8'),
                         ['https://cdn.invalid/video/init.mp4', 'https://cdn.invalid/one.m4s',
                          'https://cdn.invalid/video/two.m4s'])

    def test_hls_variants_keep_relative_urls(self):
        content = '#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=500,RESOLUTION=1280x720,CODECS="avc1"\n720/index.m3u8'
        self.assertEqual(hls_variants(content, 'https://cdn.invalid/master.m3u8'),
                         [(1280, 720, 'avc1', 'https://cdn.invalid/720/index.m3u8')])

    def test_hls_unsupported_encryption_is_explicit(self):
        with self.assertRaisesRegex(ValueError, 'Encrypted'):
            hls_segments('#EXT-X-KEY:METHOD=AES-128,URI="key"\nsegment', 'https://cdn.invalid/')

    def test_dash_inherited_time_template_and_finite_negative_repeat(self):
        manifest = '''<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" mediaPresentationDuration="PT6S">
          <BaseURL>https://cdn.invalid/</BaseURL><Period><AdaptationSet contentType="audio">
          <SegmentTemplate timescale="1" initialization="$RepresentationID$/init" media="$Time%03d$.m4s">
          <SegmentTimeline><S t="0" d="2" r="-1"/></SegmentTimeline></SegmentTemplate>
          <Representation id="audio"/></AdaptationSet></Period></MPD>'''
        self.assertEqual(dash_segments(manifest), [['https://cdn.invalid/audio/init', 'https://cdn.invalid/000.m4s',
                                                  'https://cdn.invalid/002.m4s', 'https://cdn.invalid/004.m4s']])

    def test_manual_login_preserves_supplied_refresh_token(self):
        backend = TidekeeperBackend()
        with mock.patch.dict(TOKEN.__dict__, {'refreshToken': 'old-refresh'}), \
             mock.patch.object(TIDAL_API, 'loginByAccessToken'), mock.patch.object(TOKEN, 'save'), \
             mock.patch.object(TIDAL_API, 'key', SimpleNamespace(userId=1, countryCode='US', accessToken='access', refreshToken=None)):
            backend.login_by_access_token('access', 'new-refresh')
            self.assertEqual(TOKEN.refreshToken, 'new-refresh')

    def test_verification_distinguishes_server_failure_from_bad_credentials(self):
        api = TidalAPI()
        server_error = Response(status=503, body={'error': 'Unavailable'})
        with mock.patch.object(api.session, 'get', return_value=server_error), self.assertRaises(TidalApiError):
            api.verifyAccessToken('dummy')
        self.assertTrue(server_error.closed)
        with mock.patch.object(api.session, 'get', return_value=Response(status=401)):
            self.assertFalse(api.verifyAccessToken('dummy'))
        with mock.patch.object(api.session, 'get', return_value=Response(body={'userId': 1, 'countryCode': 'US'})):
            self.assertTrue(api.verifyAccessToken('dummy'))

    def test_logout_invalidates_inflight_device_login_and_caches(self):
        api = TidalAPI()
        api.apiKey = {'clientId': 'dummy'}
        api._streamCache['old'] = 'stream'
        api._artistAlbumsCache['old'] = 'album'
        api._playbackBlockedParams.add('HIGH')
        def complete_after_logout(*args):
            api.clearSession()
            return {'user': {'userId': 1, 'countryCode': 'US'}, 'access_token': 'access',
                    'refresh_token': 'refresh', 'expires_in': 3600}
        with mock.patch.object(api, '__post__', side_effect=complete_after_logout):
            self.assertFalse(api.checkAuthStatus())
        self.assertFalse(api.key.accessToken)
        self.assertFalse(api._streamCache)
        self.assertFalse(api._artistAlbumsCache)
        self.assertFalse(api._playbackBlockedParams)

    def test_requeue_creates_independent_state_and_source(self):
        source = SearchItem(Type.Track, 'Song', '', '', '1', '', SimpleNamespace(id=1), status='Done')
        first, second = queue_item(source), queue_item(source)
        first.status = 'Failed'
        first.source.id = 2
        self.assertEqual(second.status, 'Queued')
        self.assertEqual(source.status, 'Done')
        self.assertEqual(second.source.id, 1)
        self.assertEqual(len({first.job_id, second.job_id, source.job_id}), 3)

    def test_queue_roundtrip_restores_interrupted_jobs(self):
        item = SearchItem(Type.Track, 'Song', '', '', '1', '', SimpleNamespace(id=1), status='Downloading')
        backend = TidekeeperBackend()
        with mock.patch.object(PATHS, 'getConfigDirectory', return_value=str(self.root)):
            backend.save_queue([item])
            restored = backend.load_queue()
        self.assertEqual(restored[0].status, 'Interrupted')
        self.assertEqual(restored[0].identifier, '1')
        self.assertIsNone(restored[0].source)
        self.assertEqual((self.root / '.tidekeeper-queue.json').stat().st_mode & 0o777, 0o600)

    def test_unavailable_collection_entries_reach_warning_summary(self):
        api = TidalAPI()
        warnings = []
        data = [{'type': 'track', 'item': {'id': 1, 'title': 'Unavailable', 'streamReady': False}}]
        with job_context(warning=warnings.append), mock.patch.object(api, '__getItems__', return_value=data):
            self.assertEqual(api.getItems(1, Type.Album), ([], []))
        self.assertEqual(warnings, ['Skipped unavailable track: Unavailable'])

    def test_redaction_covers_gui_and_service_token_names(self):
        message = 'accessToken="dummy-access" refresh_token=dummy-refresh Bearer dummy-bearer https://cdn.invalid/file?token=dummy-query'
        result = redact(message)
        for secret in ['dummy-access', 'dummy-refresh', 'dummy-bearer', 'dummy-query']:
            self.assertNotIn(secret, result)


if __name__ == '__main__':
    unittest.main()
