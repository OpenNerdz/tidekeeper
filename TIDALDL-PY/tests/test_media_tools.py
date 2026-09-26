"""Validate the media tool boundary with generated, freely reusable fixtures."""
import json
import copy
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import requests

from tidal_dl import download
from tidal_dl.model import StreamUrl, Video, VideoStreamUrl
from tidal_dl.settings import SETTINGS


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
        facts = download.__verifyMediaQuality__(str(self.audio()), stream)
        self.assertEqual(facts['codec'], 'flac')
        self.assertEqual(facts['sampleRate'], 48000)
        self.assertEqual(facts['verifiedBy'], 'ffprobe')

    def test_small_invalid_file_is_rejected_by_real_ffprobe(self):
        path = self.root / 'unfinished.m4a'
        path.write_bytes(b'unfinished media')
        with self.assertRaisesRegex(RuntimeError, 'ffprobe validation'):
            download.__verifyMediaQuality__(str(path), StreamUrl())

    def test_flac_container_remux_preserves_audio_quality(self):
        source = self.audio()
        container = self.root / 'wrapped.m4a'
        self.generate('-i', str(source), '-c:a', 'copy', '-strict', '-2', '-f', 'mp4', str(container))
        stream = StreamUrl()
        stream.codec, stream.container = 'flac', 'mp4'
        stream.sampleRate = 48000
        with mock.patch.object(SETTINGS, 'saveAsFlac', True):
            output = download.__exportFlacFromContainer__(str(container), stream)
        self.assertEqual(Path(output).suffix, '.flac')
        self.assertFalse(container.exists())
        facts = download.__verifyMediaQuality__(output, stream)
        self.assertEqual(facts['codec'], 'flac')
        self.assertEqual(facts['sampleRate'], 48000)

    def test_video_finalization_produces_readable_mp4(self):
        source = self.root / 'video.part'
        target = self.root / 'video.mp4'
        self.generate('-f', 'lavfi', '-i', 'color=c=blue:s=96x64:r=10:d=0.3',
                      '-c:v', 'mpeg2video', '-f', 'mpegts', str(source))
        self.assertEqual(download.__finalizeVideoFile__(str(source), str(target)), str(target))
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
                    mock.patch.object(download, '__httpRequest__', side_effect=media_response), \
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


if __name__ == '__main__':
    unittest.main()
