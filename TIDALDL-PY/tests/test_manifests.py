"""HLS and DASH manifest parsing and limits."""

import base64
import unittest
from unittest import mock

from tidal_dl import download, manifests
from tidal_dl.manifests import best_dash_representation, dash_representations, hls_segments, hls_variants
from tidal_dl.tidal import TidalStreamUnavailable

from fixtures import ApiFixture, DownloadFolderApiFixture, TransferFixture, response


class ManifestParsingTests(TransferFixture, unittest.TestCase):
    def test_hls_relative_segments_and_initialization(self):
        content = '#EXTM3U\n#EXT-X-MAP:URI="init.mp4"\n../one.m4s\ntwo.m4s\n#EXT-X-ENDLIST\n'
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
        self.assertEqual([item['urls'] for item in dash_representations(manifest)], [['https://cdn.invalid/audio/init', 'https://cdn.invalid/000.m4s',
                                                  'https://cdn.invalid/002.m4s', 'https://cdn.invalid/004.m4s']])

    def test_dash_selects_highest_fidelity_representation(self):
        manifest = '''<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" mediaPresentationDuration="PT2S">
          <Period><AdaptationSet contentType="audio" mimeType="audio/mp4">
          <SegmentTemplate timescale="1" duration="2" initialization="$RepresentationID$/init"
            media="$RepresentationID$/$Number$.m4s"/>
          <Representation id="FLAC,44100,16" codecs="flac" bandwidth="900000" audioSamplingRate="44100"/>
          <Representation id="FLAC_HIRES,192000,24" codecs="flac" bandwidth="5000000" audioSamplingRate="192000"/>
          </AdaptationSet></Period></MPD>'''
        selected = best_dash_representation(manifest)
        self.assertEqual(selected['id'], 'FLAC_HIRES,192000,24')
        self.assertEqual(selected['bitDepth'], 24)
        self.assertEqual(selected['sampleRate'], 192000)

    def test_dash_rejects_entities_and_oversized_input(self):
        with self.assertRaises(Exception):
            dash_representations('<!DOCTYPE x [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><MPD>&xxe;</MPD>')
        with self.assertRaisesRegex(ValueError, 'too large'):
            dash_representations(' ' * (2 * 1024 * 1024 + 1))

    def test_numeric_dash_ids_are_not_bit_depths(self):
        manifest = '''<MPD mediaPresentationDuration="PT2S"><Period>
          <AdaptationSet contentType="audio" mimeType="audio/mp4">
          <SegmentTemplate duration="2" initialization="$RepresentationID$/init"
            media="$RepresentationID$/$Number$.m4s"/>
          <Representation id="1" codecs="flac" audioSamplingRate="192000" bandwidth="5000000"/>
          <Representation id="2" codecs="flac" audioSamplingRate="44100" bandwidth="900000"/>
          </AdaptationSet></Period></MPD>'''
        selected = best_dash_representation(manifest)
        self.assertEqual(selected['id'], '1')
        self.assertIsNone(selected['bitDepth'])
        self.assertEqual(selected['sampleRate'], 192000)


class ManifestLimitTests(ApiFixture, unittest.TestCase):
    def test_video_master_uses_checked_transport_and_final_redirect_base(self):
        content = b'#EXTM3U\n#EXT-X-STREAM-INF:RESOLUTION=640x360\nvideo/index.m3u8\n'
        result = response(content, url='https://cdn.example/redirected/master.m3u8')
        with mock.patch.object(download, '_httpRequest', return_value=result) as request:
            variants = self.api._getResolutionList('https://cdn.example/master.m3u8')
        self.assertEqual(variants[0].m3u8Url, 'https://cdn.example/redirected/video/index.m3u8')
        self.assertTrue(request.call_args.kwargs['stream'])
        self.assertTrue(request.call_args.kwargs['allow_redirects'])
        result.close.assert_called_once()

    def test_video_master_closes_response_when_parsing_fails(self):
        result = response(b'Not a playlist')
        with mock.patch.object(download, '_httpRequest', return_value=result), self.assertRaises(ValueError):
            self.api._getResolutionList('https://cdn.example/master.m3u8')
        result.close.assert_called_once()

    def test_manifest_decode_limits_decoded_content(self):
        with mock.patch('tidal_dl.tidal.MAX_MANIFEST_BYTES', 4):
            self.assertEqual(self.api._decodeManifest(base64.b64encode(b'test').decode()), 'test')
            with self.assertRaises(TidalStreamUnavailable):
                self.api._decodeManifest(base64.b64encode(b'tests').decode())

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


class PlaylistCompletenessTests(DownloadFolderApiFixture, unittest.TestCase):
    def test_vod_without_end_marker_is_complete_but_event_is_not(self):
        for kind in ('VOD', 'EVENT', ''):
            content = f'#EXTM3U\n#EXT-X-PLAYLIST-TYPE:{kind}\n#EXTINF:1,\none.ts\n'
            if kind == 'VOD':
                self.assertEqual(manifests.hls_segments(content, 'https://cdn.example/index.m3u8'),
                                 ['https://cdn.example/one.ts'])
            else:
                with self.assertRaisesRegex(ValueError, 'Live or unfinished'):
                    manifests.hls_segments(content, 'https://cdn.example/index.m3u8')


if __name__ == "__main__":
    unittest.main()
