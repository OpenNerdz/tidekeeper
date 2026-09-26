"""Offline behavioral checks from the September 2026 repository review."""
import base64
import copy
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest import mock

import requests

import tidal_dl
from tidal_dl import download, inputs, manifests, paths, runtime
from tidal_dl.enums import AudioQuality, Type, VideoQuality
from tidal_dl.http import response_bytes
from tidal_dl.model import Album, StreamUrl, Track, VideoStreamUrl
from tidal_dl.printf import Printf
from tidal_dl.settings import SETTINGS
from tidal_dl.tidal import TidalAPI, TidalApiError, TidalStreamUnavailable


def response(content=b'', headers=None, status=200, url='https://cdn.example/media'):
    result = requests.Response()
    result.status_code = status
    result._content = content
    result._content_consumed = True
    result.headers.update(headers or {})
    result.url = url
    result.close = mock.Mock()
    return result


class ReviewHardeningTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        saved = copy.deepcopy(SETTINGS.__dict__)

        def restore():
            SETTINGS.__dict__.clear()
            SETTINGS.__dict__.update(saved)

        self.addCleanup(restore)
        self.api = TidalAPI()
        self.addCleanup(self.api.session.close)

    def test_help_and_version_do_not_read_or_write_a_profile(self):
        for flag in ('--help', '--version'):
            with self.subTest(flag=flag), mock.patch('sys.argv', ['tidekeeper', flag]), \
                    mock.patch.object(SETTINGS, 'read') as read, \
                    mock.patch.object(tidal_dl, 'configure_logging') as configure, \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(tidal_dl.main(), 0)
            read.assert_not_called()
            configure.assert_not_called()

    def test_invalid_cli_options_leave_settings_unchanged(self):
        old = dict(SETTINGS.__dict__)
        for flags in (['-o', 'different', '-q', 'typo'], ['--quality-priority', 'High,typo'],
                      ['-r', '999'], ['--quality-priority', ''], ['unrecognized'], ['--output', '']):
            with self.subTest(flags=flags), mock.patch('sys.argv', ['tidekeeper', *flags]), \
                    mock.patch.object(SETTINGS, 'save') as save, mock.patch.object(Printf, 'err'):
                self.assertEqual(tidal_dl.mainCommand(), 1)
                save.assert_not_called()
            self.assertEqual(SETTINGS.__dict__, old)

    def test_valid_cli_options_save_once(self):
        with mock.patch('sys.argv', ['tidekeeper', '-q', 'HiFi', '-r', '1080p', '--paths']), \
                mock.patch.object(SETTINGS, 'save') as save, mock.patch.object(Printf, 'paths'):
            self.assertEqual(tidal_dl.mainCommand(), 0)
        self.assertEqual(SETTINGS.audioQuality, AudioQuality.HiFi)
        self.assertEqual(SETTINGS.videoQuality, VideoQuality.P1080)
        save.assert_called_once()

    def test_cli_write_failure_rolls_back_runtime_settings(self):
        old = dict(SETTINGS.__dict__)
        with mock.patch('sys.argv', ['tidekeeper', '-q', 'Normal']), \
                mock.patch.object(SETTINGS, 'save', side_effect=OSError('Read-only folder')), \
                mock.patch.object(Printf, 'err'):
            self.assertEqual(tidal_dl.mainCommand(), 1)
        self.assertEqual(SETTINGS.__dict__, old)

    def test_option_values_are_not_mistaken_for_config_flags(self):
        with mock.patch('sys.argv', ['tidekeeper', '-o', '-collection', '--paths']), \
                mock.patch.object(paths.PATHS, 'homePathOverride', None):
            tidal_dl.preMainCommand()
            self.assertIsNone(paths.PATHS.homePathOverride)

    def test_secret_prompt_uses_hidden_input(self):
        with mock.patch('tidal_dl.printf.getpass.getpass', return_value='sample-token') as secret:
            self.assertEqual(Printf.enterSecret('Token:'), 'sample-token')
        secret.assert_called_once()

    def test_console_file_and_job_output_all_redact_credentials(self):
        message = 'accessToken=sample-access refresh_token=sample-refresh Bearer sample-bearer'
        outputs = [io.StringIO(), io.StringIO()]
        with redirect_stdout(outputs[0]):
            runtime.print(message)
        runtime.print(message, file=outputs[1])
        job_output = []
        with runtime.job_context(job_output.append):
            runtime.print(message)
        for value in [*(output.getvalue() for output in outputs), ''.join(job_output)]:
            self.assertNotIn('sample-', value)
            self.assertIn('[redacted]', value)
        self.assertEqual(runtime.redact('AccessToken good for 1 hour.'), 'AccessToken good for 1 hour.')

    def test_url_credentials_are_redacted(self):
        value = runtime.redact('https://user:sample-password@example.com/file?token=sample-query')
        self.assertNotIn('sample-', value)

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

    def test_video_master_uses_checked_transport_and_final_redirect_base(self):
        content = b'#EXTM3U\n#EXT-X-STREAM-INF:RESOLUTION=640x360\nvideo/index.m3u8\n'
        result = response(content, url='https://cdn.example/redirected/master.m3u8')
        with mock.patch.object(download, '__httpRequest__', return_value=result) as request:
            variants = self.api.__getResolutionList__('https://cdn.example/master.m3u8')
        self.assertEqual(variants[0].m3u8Url, 'https://cdn.example/redirected/video/index.m3u8')
        self.assertTrue(request.call_args.kwargs['stream'])
        self.assertTrue(request.call_args.kwargs['allow_redirects'])
        result.close.assert_called_once()

    def test_video_master_closes_response_when_parsing_fails(self):
        result = response(b'Not a playlist')
        with mock.patch.object(download, '__httpRequest__', return_value=result), self.assertRaises(ValueError):
            self.api.__getResolutionList__('https://cdn.example/master.m3u8')
        result.close.assert_called_once()

    def test_oauth_requests_do_not_follow_redirects(self):
        result = response(status=302)
        with mock.patch.object(self.api.session, 'post', return_value=result) as post, \
                self.assertRaises(TidalApiError):
            self.api.__post__('/token', {'grant_type': 'device'})
        self.assertFalse(post.call_args.kwargs['allow_redirects'])
        result.close.assert_called_once()

    def test_sign_in_address_accepts_bare_host_and_https(self):
        for uri in ('link.tidal.com', 'https://link.tidal.com'):
            grant = {'deviceCode': 'device', 'userCode': 'AB-CD', 'verificationUri': uri,
                     'expiresIn': 300, 'interval': 5}
            with self.subTest(uri=uri), mock.patch.object(self.api, '__post__', return_value=grant):
                self.assertEqual(self.api.getDeviceCode(), 'https://link.tidal.com/AB-CD')

    def test_sign_in_address_requires_expected_provider(self):
        grant = {'deviceCode': 'device', 'userCode': 'AB-CD', 'verificationUri': 'https://example.com',
                 'expiresIn': 300, 'interval': 5}
        with mock.patch.object(self.api, '__post__', return_value=grant), self.assertRaises(TidalApiError):
            self.api.getDeviceCode()

    def test_cancelled_device_request_cannot_install_a_late_challenge(self):
        def grant(*args):
            self.api.clearSession()
            return {'deviceCode': 'device', 'userCode': 'AB-CD', 'verificationUri': 'link.tidal.com',
                    'expiresIn': 300, 'interval': 5}
        with mock.patch.object(self.api, '__post__', side_effect=grant), self.assertRaises(TidalApiError):
            self.api.getDeviceCode()
        self.assertIsNone(self.api.key.deviceCode)

    def test_device_slow_down_increases_poll_interval(self):
        self.api.key.authCheckInterval = 5
        with mock.patch.object(self.api, '__post__', return_value={'error': 'slow_down'}):
            self.assertFalse(self.api.checkAuthStatus())
            self.assertEqual(self.api.key.authCheckInterval, 10)

    def test_catalog_url_requires_exact_host_and_valid_identifier(self):
        for url in ('https://example.com/browse/track/123', 'https://tidal.com/browse/track/two-words'):
            self.assertEqual(self.api.parseUrl(url), (Type.Null, url))
            with mock.patch.object(self.api, 'getTypeData') as get, self.assertRaises(ValueError):
                self.api.getByString(url)
            get.assert_not_called()
        self.assertEqual(self.api.parseUrl('https://listen.TIDAL.com/track/123'), (Type.Track, '123'))

    def test_preview_playback_is_not_downloaded_as_full_audio_or_video(self):
        payload = {'assetPresentation': 'PREVIEW'}
        with mock.patch.object(self.api, '__getPlaybackData__', return_value=payload):
            with self.assertRaises(TidalStreamUnavailable):
                self.api.__getStandardStreamUrl__(123, AudioQuality.High)
            with self.assertRaises(TidalStreamUnavailable):
                self.api.getVideoStreamUrl(123, VideoQuality.P720)

    def test_video_resolution_stays_within_selected_maximum(self):
        variants = []
        for height in (360, 1080):
            item = VideoStreamUrl()
            item.resolutions = ['1920', str(height)]
            variants.append(item)
        payload = {'manifestMimeType': 'application/vnd.tidal.emu',
                   'manifest': base64.b64encode(json.dumps({'urls': ['https://cdn.example/master']}).encode()).decode()}
        with mock.patch.object(self.api, '__getPlaybackData__', return_value=payload), \
                mock.patch.object(self.api, '__getResolutionList__', return_value=variants):
            self.assertIs(self.api.getVideoStreamUrl(1, VideoQuality.P720), variants[0])
            self.assertIs(self.api.getVideoStreamUrl(1, VideoQuality.P1080), variants[1])

    def test_manifest_decode_limits_decoded_content(self):
        with mock.patch('tidal_dl.tidal.MAX_MANIFEST_BYTES', 4):
            self.assertEqual(self.api.__decodeManifest__(base64.b64encode(b'test').decode()), 'test')
            with self.assertRaises(TidalStreamUnavailable):
                self.api.__decodeManifest__(base64.b64encode(b'tests').decode())

    def test_hls_requires_a_complete_media_playlist(self):
        for content in ('ordinary text', '#EXTM3U\nsegment.ts\n',
                        '#EXTM3U\n#EXT-X-STREAM-INF:RESOLUTION=640x360\nchild.m3u8\n'):
            with self.subTest(content=content), self.assertRaises(ValueError):
                manifests.hls_segments(content, 'https://cdn.example/index.m3u8')
        self.assertEqual(manifests.hls_segments('#EXTM3U\nsegment.ts\n#EXT-X-ENDLIST\n',
                                              'https://cdn.example/index.m3u8'),
                         ['https://cdn.example/segment.ts'])

    def test_dash_does_not_silently_drop_additional_periods(self):
        with self.assertRaisesRegex(ValueError, 'single complete period'):
            manifests.dash_representations('<MPD><Period/><Period/></MPD>')

    def test_dash_template_expansion_respects_total_budget(self):
        content = '''<MPD mediaPresentationDuration="PT4S"><Period><AdaptationSet contentType="audio">
        <SegmentTemplate duration="2" initialization="init" media="$Number$.m4s"/>
        <Representation id="audio"/></AdaptationSet></Period></MPD>'''
        with mock.patch.object(manifests, 'MAX_EXPANDED_URL_BYTES', 5), self.assertRaises(ValueError):
            manifests.dash_representations(content)

    def test_nested_list_size_is_bounded(self):
        (self.root / 'items.txt').write_text('123456789', encoding='utf-8')
        with mock.patch.object(inputs, 'MAX_LIST_BYTES', len(str(self.root / 'items.txt')) + 3), \
                self.assertRaises(ValueError):
            inputs.parse_direct_inputs(str(self.root / 'items.txt'))

    def test_list_entry_count_is_bounded(self):
        with mock.patch.object(inputs, 'MAX_INPUTS', 2), self.assertRaises(ValueError):
            inputs.parse_direct_inputs('1\n2\n3')

    def test_download_reports_response_size_before_body_progress(self):
        progress = mock.Mock()
        result = response(b'abcdef', {'Content-Length': '6'})

        def chunks(**kwargs):
            progress.setMaxNum.assert_called_with(6)
            yield b'abc'
            yield b'def'

        result.iter_content = chunks
        with mock.patch.object(download, '__httpRequest__', return_value=result) as request:
            ok, error = download.__downloadUrls__(['https://cdn.example/audio'], str(self.root / 'audio'),
                                                  userProgress=progress, probeSize=False)
        self.assertTrue(ok, error)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(sum(call.args[0] for call in progress.addCurNum.call_args_list), 6)

    def test_segment_progress_uses_sum_of_get_sizes(self):
        progress = mock.Mock()
        responses = [response(b'abc', {'Content-Length': '3'}), response(b'defg', {'Content-Length': '4'})]
        with mock.patch.object(download, '__httpRequest__', side_effect=responses):
            ok, error = download.__downloadUrls__(['https://cdn.example/one', 'https://cdn.example/two'],
                                                  str(self.root / 'audio'), userProgress=progress, probeSize=False)
        self.assertTrue(ok, error)
        self.assertEqual((self.root / 'audio').read_bytes(), b'abcdefg')
        self.assertTrue(all(call.args == (7,) for call in progress.setMaxNum.call_args_list))

    def test_cancelled_connection_slot_wait_does_not_start_transfer(self):
        cancel = threading.Event()
        cancel.set()
        with mock.patch.object(download, 'media_connection_slots', threading.BoundedSemaphore(0)), \
                mock.patch.object(download, '__httpRequest__') as request, \
                runtime.job_context(cancel=cancel), self.assertRaises(runtime.DownloadCancelled):
            download.__downloadSingleUrl__('https://cdn.example/audio', str(self.root / 'audio'))
        request.assert_not_called()

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

    def test_root_download_folder_is_preserved(self):
        track, stream = Track(), StreamUrl()
        SETTINGS.downloadPath = '/'
        SETTINGS.trackFileFormat = '{TrackID}'
        track.id = 123
        self.assertEqual(paths.getTrackPath(track, stream), '/123.m4a')

    def test_volume_labels_stay_in_one_directory_component(self):
        album, track, stream = Album(), Track(), StreamUrl()
        album.numberOfVolumes = 2
        album.releaseDate = '2026-01-01'
        track.volumeNumber = 'disc one / bonus'
        SETTINGS.downloadPath = str(self.root)
        SETTINGS.albumFolderFormat = 'album'
        SETTINGS.trackFileFormat = 'track'
        self.assertEqual(Path(paths.getTrackPath(track, stream, album)).parent.name, 'CDdisc one - bonus')

    def test_media_tools_are_limited_to_local_media_formats(self):
        source = self.root / 'audio.m4a'
        source.write_bytes(b'media fixture' * 400)
        completed = SimpleNamespace(returncode=0, stderr='', stdout=json.dumps({'streams': [{'codec_name': 'flac'}]}))
        stream = StreamUrl()
        stream.codec = 'flac'
        with mock.patch.object(download.shutil, 'which', return_value='ffprobe'), \
                mock.patch.object(download, 'run_process', return_value=completed) as process:
            download.__verifyMediaQuality__(str(source), stream)
        command = process.call_args.args[0]
        self.assertEqual(command[command.index('-protocol_whitelist') + 1], 'file')
        self.assertIn('-format_whitelist', command)

    def test_small_invalid_audio_is_still_probed(self):
        source = self.root / 'small.m4a'
        source.write_bytes(b'incomplete media')
        with mock.patch.object(download.shutil, 'which', return_value='ffprobe'), \
                mock.patch.object(download, 'run_process', return_value=SimpleNamespace(
                    returncode=1, stderr='Invalid media', stdout='')) as process, \
                self.assertRaises(RuntimeError):
            download.__verifyMediaQuality__(str(source), StreamUrl())
        process.assert_called_once()

    def test_public_media_does_not_use_automatic_netrc_credentials(self):
        with mock.patch.object(download, 'download_session_state', threading.local()):
            session = download.__httpSession__()
            try:
                with mock.patch('requests.sessions.get_netrc_auth', return_value=('user', 'sample-password')) as netrc:
                    request = session.prepare_request(requests.Request('GET', 'https://cdn.example/media'))
                netrc.assert_not_called()
                self.assertNotIn('Authorization', request.headers)
            finally:
                session.close()


if __name__ == '__main__':
    unittest.main()
