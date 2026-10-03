"""Resumable media transfers, completion receipts, and HTTP handling."""

import json
import os
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import requests

from tidal_dl import download, runtime
from tidal_dl.enums import VideoQuality
from tidal_dl.http import response_bytes
from tidal_dl.runtime import DownloadCancelled, job_context
from tidal_dl.settings import SETTINGS
from tidal_dl.tidal import TIDAL_API
from tidal_dl.transfer_state import (
    is_completed,
    prepare_transfer,
    record_completion,
    video_identity,
)

from fixtures import (
    ApiFixture,
    DownloadFolderApiFixture,
    FakeResponse,
    ProfileFixture,
    TransferFixture,
    response,
)


class ResumeAndReceiptTests(TransferFixture, unittest.TestCase):
    def test_changed_stream_discards_numbered_segments(self):
        path = str(self.root / 'video.part')
        prepare_transfer(path, ['https://cdn.invalid/old0', 'https://cdn.invalid/old1'])
        parts = Path(path + '.parts')
        parts.mkdir()
        (parts / '000000.part').write_bytes(b'OLD')
        Path(path).write_bytes(b'OLD-STREAM')
        with mock.patch.object(download, '_httpRequest', side_effect=[FakeResponse(b'NEW'), FakeResponse(b'DATA')]):
            ok, message = download._downloadUrls(['https://cdn.invalid/new0', 'https://cdn.invalid/new1'],
                                                   path, threadNum=1, probeSize=False)
        self.assertTrue(ok, message)
        self.assertEqual(Path(path).read_bytes(), b'NEWDATA')

    def test_failed_changed_stream_does_not_reuse_old_output_on_retry(self):
        for segmented in (False, True):
            with self.subTest(segmented=segmented):
                path = str(self.root / ('segmented' if segmented else 'single'))
                Path(path).write_bytes(b'OLD-DATA')
                urls = ['https://cdn.invalid/new0']
                if segmented:
                    urls.append('https://cdn.invalid/new1')
                error = requests.HTTPError('404', response=FakeResponse(status=404))
                with mock.patch.object(download, '_httpRequest', side_effect=error):
                    ok, _ = download._downloadUrls(urls, path, probeSize=False, expectedSize=8)
                self.assertFalse(ok)
                self.assertEqual(Path(path).read_bytes(), b'OLD-DATA')
                responses = [FakeResponse(b'NEW-'), FakeResponse(b'DATA')] if segmented else [FakeResponse(b'NEW-DATA')]
                with mock.patch.object(download, '_httpRequest', side_effect=responses):
                    ok, message = download._downloadUrls(urls, path, probeSize=False, expectedSize=8)
                self.assertTrue(ok, message)
                self.assertEqual(Path(path).read_bytes(), b'NEW-DATA')

    def test_signed_urls_are_hashed_on_disk(self):
        path = str(self.root / 'part')
        prepare_transfer(path, ['https://cdn.invalid/file?signature=dummy-secret'])
        self.assertNotIn('dummy-secret', Path(path + '.source.json').read_text())

    def test_refreshed_signature_keeps_resumable_segments(self):
        path = str(self.root / 'part')
        prepare_transfer(path, ['https://cdn.invalid/media?token=first&format=flac'])
        parts = Path(path + '.parts')
        parts.mkdir()
        completed = parts / '00000000.part'
        completed.write_bytes(b'complete')
        prepare_transfer(path, ['https://cdn.invalid/media?token=second&format=flac'])
        self.assertTrue(completed.exists())
        prepare_transfer(path, ['https://cdn.invalid/media?token=third&format=aac'])
        self.assertFalse(parts.exists())

    def test_matching_416_promotes_complete_partial(self):
        path = str(self.root / 'part')
        urls = ['https://cdn.invalid/file']
        prepare_transfer(path, urls)
        Path(path + '.download').write_bytes(b'complete')
        response = FakeResponse(status=416, headers={'Content-Range': 'bytes */8'})
        error = requests.HTTPError('416', response=response)
        with mock.patch.object(download, '_httpRequest', side_effect=error):
            ok, message = download._downloadUrls(urls, path, probeSize=False, expectedSize=8)
        self.assertTrue(ok, message)
        self.assertEqual(Path(path).read_bytes(), b'complete')

    def test_overlong_416_restarts_transfer(self):
        path = str(self.root / 'part')
        urls = ['https://cdn.invalid/file']
        prepare_transfer(path, urls)
        Path(path + '.download').write_bytes(b'overlong-data')
        error = requests.HTTPError('416', response=FakeResponse(status=416, headers={'Content-Range': 'bytes */3'}))
        with mock.patch.object(download, '_httpRequest', side_effect=[error, FakeResponse(b'new')]):
            ok, message = download._downloadUrls(urls, path, probeSize=False, expectedSize=3)
        self.assertTrue(ok, message)
        self.assertEqual(Path(path).read_bytes(), b'new')

    def test_truncated_flac_is_not_skipped(self):
        SETTINGS.checkExist = SETTINGS.saveAsFlac = True
        path = str(self.root / 'track.flac')
        Path(path).write_bytes(b'fLaC' + b'\0' * 2048)
        stream = SimpleNamespace(trackid=1, soundQuality='LOSSLESS', codec='flac', container='mp4')
        self.assertEqual(download._existingMediaState(path, stream), (None, False))

    def test_receipt_rejects_tampering_and_different_quality(self):
        path = str(self.root / 'track.flac')
        Path(path).write_bytes(b'media')
        identity = {'type': 'track', 'id': '1', 'quality': 'LOSSLESS'}
        record_completion(path, identity)
        self.assertTrue(is_completed(path, identity))
        self.assertFalse(is_completed(path, dict(identity, quality='HIGH')))
        Path(path).write_bytes(b'other')
        self.assertFalse(is_completed(path, identity))

    def test_legacy_completion_receipt_remains_valid(self):
        path = str(self.root / 'track.flac')
        Path(path).write_bytes(b'media')
        identity = {'type': 'track', 'id': '1'}
        record_completion(path, identity)
        receipt_path = Path(path + '.tidekeeper.json')
        receipt = json.loads(receipt_path.read_text())
        del receipt['metadata_complete']
        receipt_path.write_text(json.dumps(receipt))
        self.assertTrue(is_completed(path, identity))

    def test_parallel_size_probes_observe_inflight_cancellation(self):
        cancelled = threading.Event()
        started = threading.Barrier(2)

        def response(*args, **kwargs):
            started.wait(timeout=3)
            cancelled.set()
            return FakeResponse(status=503)

        # Both probes reach HTTP before cancellation, then must interrupt their
        # retry wait rather than lose the job context in the nested executor.
        with job_context(cancel=cancelled), \
             mock.patch.object(download, '_httpSession') as session:
            session.return_value.request.side_effect = response
            with self.assertRaises(DownloadCancelled):
                download._remoteSize(['https://cdn.invalid/1', 'https://cdn.invalid/2'])
            self.assertEqual(session.return_value.request.call_count, 2)

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

    def test_cancel_during_transfer_keeps_partial_and_existing_output(self):
        path = str(self.root / 'track')
        Path(path).write_bytes(b'previous-good')
        cancelled = threading.Event()
        class Interrupted(FakeResponse):
            def iter_content(self, chunk_size):
                yield b'first'
                cancelled.set()
                yield b'second'
        with job_context(cancel=cancelled), mock.patch.object(download, '_httpRequest', return_value=Interrupted()):
            with self.assertRaises(DownloadCancelled):
                download._downloadUrls(['https://cdn.invalid/file'], path, probeSize=False)
        self.assertEqual(Path(path).read_bytes(), b'previous-good')
        self.assertEqual(Path(path + '.download').read_bytes(), b'first')

    def test_cancel_after_last_chunk_preserves_existing_output(self):
        path = str(self.root / 'track')
        Path(path).write_bytes(b'previous-good')
        cancelled = threading.Event()

        class CancelAtEnd(FakeResponse):
            def iter_content(self, chunk_size):
                yield b'complete'
                cancelled.set()

        with job_context(cancel=cancelled), \
                mock.patch.object(download, '_httpRequest', return_value=CancelAtEnd(b'complete')):
            with self.assertRaises(DownloadCancelled):
                download._downloadUrls(['https://cdn.invalid/file'], path, probeSize=False)
        self.assertEqual(Path(path).read_bytes(), b'previous-good')
        self.assertEqual(Path(path + '.download').read_bytes(), b'complete')


class AssemblyCancellationTests(ProfileFixture, unittest.TestCase):
    def test_cancelled_assembly_preserves_output_and_removes_temporary_file(self):
        source = self.root / 'part'
        output = self.root / 'result'
        source.write_bytes(b'new data')
        output.write_bytes(b'previous data')
        with mock.patch.object(download, 'check_cancelled', side_effect=DownloadCancelled):
            with self.assertRaises(DownloadCancelled):
                download._concatenateFiles([str(source)], str(output))
        self.assertEqual(output.read_bytes(), b'previous data')
        self.assertFalse(Path(f'{output}.tmp.{os.getpid()}').exists())
        self.assertEqual(source.read_bytes(), b'new data')


class ResponseAndProgressTests(ApiFixture, unittest.TestCase):
    def test_bounded_response_reads_normal_content(self):
        self.assertEqual(response_bytes(response(b'abcdef'), 6), b'abcdef')

    def test_bounded_response_checks_headers_before_reading(self):
        result = response(b'', {'Content-Length': '7'})
        with mock.patch.object(result, 'iter_content') as read, self.assertRaises(ValueError):
            response_bytes(result, 6)
        read.assert_not_called()

    def test_bounded_response_checks_actual_bytes_without_length(self):
        with self.assertRaises(ValueError):
            response_bytes(response(b'abcdefg'), 6)

    def test_bounded_response_observes_cancellation(self):
        cancel = threading.Event()
        cancel.set()
        with runtime.job_context(cancel=cancel), self.assertRaises(runtime.DownloadCancelled):
            response_bytes(response(b'normal content'), 100)

    def test_download_reports_response_size_before_body_progress(self):
        progress = mock.Mock()
        result = response(b'abcdef', {'Content-Length': '6'})

        def chunks(**kwargs):
            progress.setMaxNum.assert_called_with(6)
            yield b'abc'
            yield b'def'

        result.iter_content = chunks
        with mock.patch.object(download, '_httpRequest', return_value=result) as request:
            ok, error = download._downloadUrls(['https://cdn.example/audio'], str(self.root / 'audio'),
                                                  userProgress=progress, probeSize=False)
        self.assertTrue(ok, error)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(sum(call.args[0] for call in progress.addCurNum.call_args_list), 6)

    def test_segment_progress_uses_sum_of_get_sizes(self):
        progress = mock.Mock()
        responses = [response(b'abc', {'Content-Length': '3'}), response(b'defg', {'Content-Length': '4'})]
        with mock.patch.object(download, '_httpRequest', side_effect=responses):
            ok, error = download._downloadUrls(['https://cdn.example/one', 'https://cdn.example/two'],
                                                  str(self.root / 'audio'), userProgress=progress, probeSize=False)
        self.assertTrue(ok, error)
        self.assertEqual((self.root / 'audio').read_bytes(), b'abcdefg')
        self.assertTrue(all(call.args == (7,) for call in progress.setMaxNum.call_args_list))

    def test_cancelled_connection_slot_wait_does_not_start_transfer(self):
        cancel = threading.Event()
        cancel.set()
        with mock.patch.object(download, 'media_connection_slots', threading.BoundedSemaphore(0)), \
                mock.patch.object(download, '_httpRequest') as request, \
                runtime.job_context(cancel=cancel), self.assertRaises(runtime.DownloadCancelled):
            download._downloadSingleUrl('https://cdn.example/audio', str(self.root / 'audio'))
        request.assert_not_called()


class RangeAndRedirectTests(DownloadFolderApiFixture, unittest.TestCase):
    def test_fresh_encoded_response_does_not_use_compressed_expected_size(self):
        target = self.root / 'audio.part'
        result = response(b'fresh', headers={'Content-Encoding': 'gzip', 'Content-Length': '25'})
        result.iter_content = mock.Mock(side_effect=lambda **kwargs: iter([b'fresh']))
        with mock.patch.object(download, '_httpRequest', return_value=result), \
                mock.patch.object(download, 'cancellable_sleep'):
            self.assertEqual(download._downloadSingleUrl(
                'https://cdn.example/audio', str(target), expectedSize=25), 5)
        self.assertEqual(target.read_bytes(), b'fresh')

    def test_fresh_encoded_response_is_decoded_and_saved(self):
        target = self.root / 'audio.part'
        result = response(b'fresh', headers={'Content-Encoding': 'gzip', 'Content-Length': '25'})
        result.iter_content = mock.Mock(return_value=iter([b'fresh']))
        with mock.patch.object(download, '_httpRequest', return_value=result):
            self.assertEqual(download._downloadSingleUrl('https://cdn.example/audio', str(target)), 5)
        self.assertEqual(target.read_bytes(), b'fresh')

    def test_encoded_response_preserves_resume_file_and_closes_response(self):
        target = self.root / 'audio.part'
        partial = Path(str(target) + '.download')
        partial.write_bytes(b'valid-prefix')
        result = response(b'unused', status=206, headers={
            'Content-Encoding': 'gzip', 'Content-Range': 'bytes 12-19/20',
        })
        result.iter_content = mock.Mock()
        with mock.patch.object(download, '_httpRequest', return_value=result) as request:
            with self.assertRaisesRegex(ValueError, 'encoded response'):
                download._downloadSingleUrl('https://cdn.example/audio', str(target))
        self.assertEqual(partial.read_bytes(), b'valid-prefix')
        result.iter_content.assert_not_called()
        result.close.assert_called_once()
        self.assertEqual(request.call_args.kwargs['headers'],
                         {'Accept-Encoding': 'identity', 'Range': 'bytes=12-'})

    def test_unexpected_initial_range_is_rejected_before_body_write(self):
        target = self.root / 'audio.part'
        result = response(b'unused', status=206, headers={'Content-Range': 'bytes 4-9/10'})
        result.iter_content = mock.Mock()
        with mock.patch.object(download, '_httpRequest', return_value=result):
            with self.assertRaisesRegex(ValueError, 'unexpected byte range'):
                download._downloadSingleUrl('https://cdn.example/audio', str(target))
        result.iter_content.assert_not_called()
        result.close.assert_called_once()
        self.assertFalse(target.exists())
        self.assertFalse(Path(str(target) + '.download').exists())

    def test_https_redirect_downgrade_is_rejected_without_second_request(self):
        result = response(status=302, headers={'Location': 'http://cdn.example/audio'})
        session = mock.Mock()
        session.request.return_value = result
        with mock.patch.object(download, '_httpSession', return_value=session), \
                mock.patch.object(download, 'validate_media_url'):
            with self.assertRaisesRegex(ValueError, 'downgrade'):
                download._httpRequest('GET', 'https://cdn.example/audio', allow_redirects=True)
        session.request.assert_called_once()
        result.close.assert_called_once()

    def test_https_redirect_still_downloads_and_closes_each_response(self):
        first = response(status=302, headers={'Location': 'https://cdn.example/final'})
        second = response(b'audio', headers={'Content-Length': '5'})
        session = mock.Mock()
        session.request.side_effect = [first, second]
        with mock.patch.object(download, '_httpSession', return_value=session), \
                mock.patch.object(download, 'validate_media_url'):
            target = self.root / 'audio'
            self.assertEqual(download._downloadSingleUrl('https://cdn.example/audio', str(target)), 5)
        self.assertEqual(target.read_bytes(), b'audio')
        first.close.assert_called_once()
        second.close.assert_called_once()
        self.assertEqual(session.request.call_count, 2)


if __name__ == "__main__":
    unittest.main()
