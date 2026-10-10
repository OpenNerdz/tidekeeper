"""Validate the media tool boundary with generated, freely reusable fixtures."""

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import requests

from tidal_dl import download, runtime
from tidal_dl.model import StreamUrl, Video, VideoStreamUrl
from tidal_dl.runtime import DownloadCancelled, job_context, run_process
from tidal_dl.settings import SETTINGS
from tidal_dl.tidal import TidalAPI

from fixtures import ApiFixture, ProfileFixture, TransferFixture


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg and ffprobe are required')
class MediaToolIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def generate(self, *args):
        subprocess.run([shutil.which('ffmpeg'), '-nostdin', '-v', 'error', '-y', *args],
                       check=True, capture_output=True, timeout=30)

    def audio(self):
        path = self.root / 'tone.flac'
        self.generate('-f', 'lavfi', '-i', 'sine=frequency=440:duration=0.15',
                      '-ar', '48000', '-c:a', 'flac', str(path))
        return path

    def test_generated_flac_passes_audio_verification(self):
        stream = StreamUrl()
        stream.codec = 'flac'
        stream.sampleRate = 48000
        facts = download._verifyMediaQuality(str(self.audio()), stream)
        self.assertEqual(facts['codec'], 'flac')
        self.assertEqual(facts['sampleRate'], 48000)
        self.assertEqual(facts['verifiedBy'], 'ffprobe')

    def test_small_invalid_file_is_rejected_by_real_ffprobe(self):
        path = self.root / 'unfinished.m4a'
        path.write_bytes(b'unfinished media')
        with self.assertRaisesRegex(RuntimeError, 'ffprobe validation'):
            download._verifyMediaQuality(str(path), StreamUrl())

    def test_flac_container_remux_preserves_audio_quality(self):
        source = self.audio()
        container = self.root / 'wrapped.m4a'
        self.generate('-i', str(source), '-c:a', 'copy', '-strict', '-2', '-f', 'mp4', str(container))
        stream = StreamUrl()
        stream.codec, stream.container = 'flac', 'mp4'
        stream.sampleRate = 48000
        with mock.patch.object(SETTINGS, 'saveAsFlac', True):
            output = download._exportFlacFromContainer(str(container), stream)
        self.assertEqual(Path(output).suffix, '.flac')
        self.assertFalse(container.exists())
        facts = download._verifyMediaQuality(output, stream)
        self.assertEqual(facts['codec'], 'flac')
        self.assertEqual(facts['sampleRate'], 48000)

    def test_video_finalization_produces_readable_mp4(self):
        source = self.root / 'video.part'
        target = self.root / 'video.mp4'
        self.generate('-f', 'lavfi', '-i', 'color=c=blue:s=96x64:r=10:d=0.3',
                      '-c:v', 'mpeg2video', '-f', 'mpegts', str(source))
        self.assertEqual(download._finalizeVideoFile(str(source), str(target)), str(target))
        self.assertFalse(source.exists())
        result = subprocess.run([shutil.which('ffprobe'), '-v', 'error', '-show_entries',
                                 'stream=codec_type', '-of', 'json', str(target)],
                                check=True, capture_output=True, timeout=30, text=True)
        self.assertEqual(json.loads(result.stdout)['streams'][0]['codec_type'], 'video')

    def test_generated_vod_without_end_marker_downloads_to_complete_mp4(self):
        playlist = self.root / 'index.m3u8'
        self.generate('-f', 'lavfi', '-i', 'color=c=blue:s=96x64:r=10:d=2',
                      '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2',
                      '-c:v', 'mpeg2video', '-c:a', 'aac', '-hls_time', '1',
                      '-hls_playlist_type', 'vod', '-hls_segment_filename',
                      str(self.root / 'part%03d.ts'), '-f', 'hls', str(playlist))
        content = playlist.read_bytes().replace(b'#EXT-X-ENDLIST', b'')
        self.assertIn(b'#EXT-X-PLAYLIST-TYPE:VOD', content)
        sources = {'index.m3u8': content}
        sources.update((path.name, path.read_bytes()) for path in self.root.glob('*.ts'))
        responses = []
        def media_response(method, url, **kwargs):
            result = requests.Response()
            result.status_code = 200
            result.url = url
            result._content = sources[url.rsplit('/', 1)[-1]]
            result._content_consumed = True
            result.headers['Content-Length'] = str(len(result._content))
            responses.append(result)
            return result
        video = Video()
        video.id, video.title, video.duration = 1, 'Generated video', 2
        stream = VideoStreamUrl()
        stream.m3u8Url = 'https://cdn.example/index.m3u8'
        target = self.root / 'complete.mp4'
        saved = copy.deepcopy(SETTINGS.__dict__)
        try:
            SETTINGS.checkExist = SETTINGS.showProgress = False
            with mock.patch.object(download.TIDAL_API, 'getVideoStreamUrl', return_value=stream), \
                    mock.patch.object(download, 'getVideoPath', return_value=str(target)), \
                    mock.patch.object(download, '_httpRequest', side_effect=media_response), \
                    mock.patch.object(download.Printf, 'video'):
                ok, message = download.downloadVideo(video)
            self.assertTrue(ok, message)
            result = subprocess.run([shutil.which('ffprobe'), '-v', 'error', '-show_entries',
                                     'format=duration:stream=codec_type', '-of', 'json', str(target)],
                                    check=True, capture_output=True, timeout=30, text=True)
            facts = json.loads(result.stdout)
            self.assertGreaterEqual(float(facts['format']['duration']), 1.9)
            self.assertEqual({item['codec_type'] for item in facts['streams']}, {'audio', 'video'})
            self.assertEqual(len(responses), len(sources))
        finally:
            SETTINGS.__dict__.clear()
            SETTINGS.__dict__.update(saved)


class MediaProcessingTests(TransferFixture, unittest.TestCase):
    def test_video_remux_failure_preserves_both_files(self):
        part, final = self.root / 'video.part', self.root / 'video.mp4'
        part.write_bytes(b'transport-stream')
        final.write_bytes(b'previous-good-video')
        with mock.patch.object(download.shutil, 'which', return_value='ffmpeg'), \
             mock.patch.object(download.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stderr=b'bad stream')):
            with self.assertRaisesRegex(RuntimeError, 'Video conversion failed'):
                download._finalizeVideoFile(str(part), str(final))
        self.assertEqual(part.read_bytes(), b'transport-stream')
        self.assertEqual(final.read_bytes(), b'previous-good-video')

    def test_missing_ffmpeg_does_not_create_fake_mp4(self):
        part, final = self.root / 'video.part', self.root / 'video.mp4'
        part.write_bytes(b'transport-stream')
        with mock.patch.object(download.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'ffmpeg'):
                download._finalizeVideoFile(str(part), str(final))
        self.assertTrue(part.exists())
        self.assertFalse(final.exists())

    def test_media_process_is_stopped_on_cancellation(self):
        cancelled = threading.Event()
        timer = threading.Timer(0.1, cancelled.set)
        timer.start()
        try:
            with job_context(cancel=cancelled), self.assertRaises(DownloadCancelled):
                run_process([sys.executable, '-c', 'import time; time.sleep(30)'], timeout=3)
        finally:
            timer.cancel()

    def test_media_tools_do_not_open_console_windows_on_windows(self):
        no_window = 0x08000000
        completed = subprocess.CompletedProcess(['ffmpeg'], 0, b'', b'')
        with mock.patch.object(runtime, '_NO_WINDOW', no_window), \
             mock.patch.object(runtime.subprocess, 'run', return_value=completed) as run:
            run_process(['ffmpeg'], capture_output=True, creationflags=0x200)
        self.assertEqual(run.call_args.kwargs['creationflags'], no_window | 0x200)

        process = mock.MagicMock(returncode=0)
        process.communicate.return_value = (b'', b'')
        with mock.patch.object(runtime, '_NO_WINDOW', no_window), \
             mock.patch.object(runtime.subprocess, 'Popen') as popen, \
             job_context(cancel=threading.Event()):
            popen.return_value.__enter__.return_value = process
            run_process(['ffprobe'], capture_output=True)
        self.assertEqual(popen.call_args.kwargs['creationflags'], no_window)

    def test_media_tools_keep_default_process_flags_elsewhere(self):
        completed = subprocess.CompletedProcess(['ffmpeg'], 0, b'', b'')
        with mock.patch.object(runtime, '_NO_WINDOW', 0), \
             mock.patch.object(runtime.subprocess, 'run', return_value=completed) as run:
            run_process(['ffmpeg'], capture_output=True)
        self.assertNotIn('creationflags', run.call_args.kwargs)

    def test_numeric_dash_id_does_not_reject_valid_probed_audio(self):
        manifest = '''<MPD mediaPresentationDuration="PT2S"><Period>
          <AdaptationSet contentType="audio" mimeType="audio/mp4">
          <SegmentTemplate duration="2" initialization="init" media="$Number$.m4s"/>
          <Representation id="99" codecs="flac" audioSamplingRate="44100"/>
          </AdaptationSet></Period></MPD>'''
        api = TidalAPI()
        self.addCleanup(api.session.close)
        stream = api._dashStreamUrl('1', 'LOSSLESS', manifest)
        probe = SimpleNamespace(returncode=0, stdout=json.dumps({'streams': [{
            'codec_name': 'flac', 'sample_rate': '44100', 'bits_per_raw_sample': '16', 'channels': 2,
        }]}))
        with mock.patch.object(download, '_localFileSize', return_value=8192), \
                mock.patch.object(download.shutil, 'which', return_value='ffprobe'), \
                mock.patch.object(download, 'run_process', return_value=probe):
            facts = download._verifyMediaQuality('fixture.flac', stream)
        self.assertEqual(facts['bitDepth'], 16)
        self.assertEqual(facts['verifiedBy'], 'ffprobe')


class FlacExportCancellationTests(ProfileFixture, unittest.TestCase):
    def test_cancelled_flac_export_cleans_up_ffmpeg_output(self):
        SETTINGS.saveAsFlac = True
        source = self.root / 'track.m4a'
        source.write_bytes(b'media')
        temporary = self.root / f'track.flac.tmp.{os.getpid()}.flac'

        def cancel(*args, **kwargs):
            temporary.write_bytes(b'incomplete')
            raise DownloadCancelled()

        stream = SimpleNamespace(codec='flac', container='mp4', manifestMimeType='')
        with mock.patch.object(download.shutil, 'which', return_value='ffmpeg'), \
             mock.patch.object(download, 'run_process', side_effect=cancel), self.assertRaises(DownloadCancelled):
            download._exportFlacFromContainer(str(source), stream)
        self.assertFalse(temporary.exists())
        self.assertEqual(source.read_bytes(), b'media')


class MediaToolSafetyTests(ApiFixture, unittest.TestCase):
    def test_media_tools_are_limited_to_local_media_formats(self):
        source = self.root / 'audio.m4a'
        source.write_bytes(b'media fixture' * 400)
        completed = SimpleNamespace(returncode=0, stderr='', stdout=json.dumps({'streams': [{'codec_name': 'flac'}]}))
        stream = StreamUrl()
        stream.codec = 'flac'
        with mock.patch.object(download.shutil, 'which', return_value='ffprobe'), \
                mock.patch.object(download, 'run_process', return_value=completed) as process:
            download._verifyMediaQuality(str(source), stream)
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
            download._verifyMediaQuality(str(source), StreamUrl())
        process.assert_called_once()

if __name__ == '__main__':
    unittest.main()
