import json
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

import requests

from tidal_dl import download
from tidal_dl.runtime import DownloadCancelled, job_context
from tidal_dl.settings import SETTINGS
from tidal_dl.tidal import TidalAPI, TidalApiError


def response(status=200, payload=None, headers=None, content=None):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(payload or {}).encode() if content is None else content
    result._content_consumed = True
    result.headers.update(headers or {})
    result.close = mock.Mock()
    return result


class HttpReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.api = TidalAPI()
        self.addCleanup(self.api.session.close)
        printer = mock.patch('tidal_dl.tidal.print')
        printer.start()
        self.addCleanup(printer.stop)
        for name, value in [('downloadDelay', False), ('adaptiveRateLimit', False)]:
            patcher = mock.patch.object(SETTINGS, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_rate_limit_exhaustion_stops_without_extra_requests(self):
        limited = response(429, headers={'Retry-After': '60'})
        with mock.patch.object(self.api.session, 'get', return_value=limited) as get, \
                mock.patch('tidal_dl.tidal.cancellable_sleep') as sleep:
            with self.assertRaises(TidalApiError) as error:
                self.api.__getOnce__('albums/1')
        self.assertEqual(error.exception.statusCode, 429)
        self.assertEqual(get.call_count, 2)
        sleep.assert_called_once_with(60)

    def test_zero_retry_delay_cannot_disable_wait_budget(self):
        limited = response(429, headers={'Retry-After': '0'})
        success = response(payload={'id': 1})
        with mock.patch.object(self.api.session, 'get', side_effect=[limited] * 100 + [success]), \
                mock.patch('tidal_dl.tidal.cancellable_sleep'):
            with self.assertRaises(TidalApiError) as error:
                self.api.__getOnce__('albums/1')
        self.assertEqual(error.exception.statusCode, 429)

    def test_playback_rate_limit_does_not_start_another_endpoint_budget(self):
        limited = TidalApiError('Too many requests', 429)
        with mock.patch.object(self.api, '__getOnce__', side_effect=limited) as get:
            with self.assertRaises(TidalApiError):
                self.api.__getPlaybackData__(1, {})
        get.assert_called_once()

    def test_catalog_closes_success_and_failure_responses(self):
        for status in (200, 403):
            with self.subTest(status=status):
                result = response(status, {'id': 1})
                with mock.patch.object(self.api.session, 'get', return_value=result):
                    if status == 200:
                        self.assertEqual(self.api.__getOnce__('albums/1'), {'id': 1})
                    else:
                        with self.assertRaises(TidalApiError):
                            self.api.__getOnce__('albums/1')
                result.close.assert_called()

    def test_manifest_closes_success_and_failure_responses(self):
        for status in (200, 403):
            with self.subTest(status=status):
                result = response(status, {'data': {'attributes': {'manifest': 'ok'}}})
                with mock.patch.object(self.api.session, 'get', return_value=result):
                    if status == 200:
                        self.assertEqual(self.api.__getOpenApiTrackManifestOnce__(1, ['FLAC'], 'DOWNLOAD'),
                                         {'manifest': 'ok'})
                    else:
                        with self.assertRaises(TidalApiError):
                            self.api.__getOpenApiTrackManifestOnce__(1, ['FLAC'], 'DOWNLOAD')
                result.close.assert_called()

    def test_size_probe_does_not_treat_partial_length_as_object_size(self):
        head = response(headers={})
        partial = response(206, headers={'Content-Range': 'bytes 0-0/*', 'Content-Length': '1'})
        with mock.patch.object(download, '__httpRequest__', side_effect=[head, partial]):
            self.assertEqual(download.__contentLength__('https://example.invalid/media'), -1)
        head.close.assert_called_once()
        partial.close.assert_called_once()

    def test_cdn_retry_budget_is_not_multiplied_by_nested_request_loop(self):
        session = mock.Mock()
        session.request.side_effect = lambda *args, **kwargs: response(503)
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(download, '__httpSession__', return_value=session), \
                mock.patch.object(download, 'cancellable_sleep'):
            path = Path(directory) / 'track.part'
            with self.assertRaises(requests.HTTPError):
                download.__downloadSingleUrl__('https://example.invalid/media', str(path))
            self.assertFalse(path.exists())
        self.assertEqual(session.request.call_count, download.DOWNLOAD_RETRIES)

    def test_retry_after_accepts_dates_and_bounds_invalid_delays(self):
        now = 1700000000
        future = format_datetime(datetime.fromtimestamp(now + 12, timezone.utc), usegmt=True)
        cases = [(future, 12), ('12', 12), ('0', 0), ('-2', 5), ('nan', 5),
                 ('inf', 5), ('invalid', 5), ('9999', 300)]
        for header, expected in cases:
            with self.subTest(header=header), mock.patch('tidal_dl.http.time.time', return_value=now):
                result = response(503, headers={'Retry-After': header})
                self.assertEqual(self.api.__retryAfter__(result, 0), max(1, expected))
                # CDN requests use the same parser with a smaller cap/default.
                from tidal_dl.http import retry_delay
                self.assertEqual(retry_delay(result, default=5, cap=60), min(expected, 60))

    def test_cancelled_auth_request_does_not_contact_server(self):
        cancel = threading.Event()
        cancel.set()
        with job_context(cancel=cancel), mock.patch.object(self.api.session, 'post') as post:
            with self.assertRaises(DownloadCancelled):
                self.api.__post__('/token', {})
        post.assert_not_called()

    def test_non_object_error_body_is_handled_as_http_error(self):
        result = response(401, content=b'[]')
        with mock.patch.object(self.api.session, 'get', return_value=result), \
                mock.patch.object(self.api, '__refreshSavedAccessToken__', return_value=False):
            with self.assertRaises(TidalApiError) as error:
                self.api.__getOnce__('tracks/1/playbackinfopostpaywall/v4')
        self.assertEqual(error.exception.statusCode, 401)
        result.close.assert_called()

    def test_cdn_transport_does_not_hide_extra_retries(self):
        with mock.patch.object(download, 'download_session_state', threading.local()):
            session = download.__httpSession__()
            try:
                self.assertEqual(session.get_adapter('https://').max_retries.total, 0)
            finally:
                session.close()

    def test_restarted_transfer_does_not_double_count_progress(self):
        first = response(headers={'Content-Length': '6'})

        def interrupted(chunk_size):
            yield b'abc'
            raise requests.ConnectionError('Connection dropped')

        first.iter_content = interrupted
        second = response(headers={'Content-Length': '6'}, content=b'abcdef')
        second.iter_content = mock.Mock(return_value=iter([b'abc', b'def']))
        progress = mock.Mock()
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(download, '__httpRequest__', side_effect=[first, second]), \
                mock.patch.object(download, 'cancellable_sleep'):
            path = Path(directory) / 'track.part'
            self.assertEqual(download.__downloadSingleUrl__('https://example.invalid/media', str(path),
                                                           userProgress=progress), 6)
            self.assertEqual(path.read_bytes(), b'abcdef')
        self.assertEqual(sum(call.args[0] for call in progress.addCurNum.call_args_list), 6)

    def test_empty_unknown_size_transfer_is_not_promoted(self):
        empty = response(content=b'')
        empty.iter_content = mock.Mock(side_effect=lambda **kwargs: iter(()))
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(download, '__httpRequest__', return_value=empty), \
                mock.patch.object(download, 'cancellable_sleep'):
            path = Path(directory) / 'track.part'
            with self.assertRaises(OSError):
                download.__downloadSingleUrl__('https://example.invalid/media', str(path))
            self.assertFalse(path.exists())


if __name__ == '__main__':
    unittest.main()
