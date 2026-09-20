"""Issue #65: a freshly authorized account must survive a playback rejection."""
import base64
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlsplit

import requests
from mutagen.flac import FLAC

from tidal_dl import download, events, paths
from tidal_dl.enums import AudioQuality
from tidal_dl.runtime import DownloadCancelled, job_context
from tidal_dl.settings import SETTINGS, TokenSettings
from tidal_dl.tidal import TidalAPI, TidalApiError, TidalStreamUnavailable


def response(status=200, payload=None):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(payload or {}).encode()
    result._content_consumed = True
    result.close = mock.Mock()
    return result


def rejected():
    return response(404, {
        'status': 404, 'subStatus': 4022,
        'userMessage': 'Client referenced in the request does not seem to exist.',
    })


def playback(quality='LOSSLESS'):
    manifest = base64.b64encode(json.dumps({
        'codecs': 'flac', 'mimeType': 'audio/flac',
        'urls': ['https://audio.example/track.flac'],
    }).encode()).decode()
    return response(payload={
        'trackid': 465909959, 'audioQuality': quality,
        'manifestMimeType': 'application/vnd.tidal.bt', 'manifest': manifest,
    })


def openapi(protected=False):
    mpd = '''<MPD xmlns="urn:mpeg:dash:schema:mpd:2011"><Period>
      <AdaptationSet contentType="audio"><Representation codecs="flac">
        <SegmentTemplate initialization="https://audio.example/init.mp4"
          media="https://audio.example/$Number$.mp4" startNumber="1">
          <SegmentTimeline><S d="48000" r="1" /></SegmentTimeline>
        </SegmentTemplate>
      </Representation></AdaptationSet></Period></MPD>'''
    if protected:
        mpd = mpd.replace('<AdaptationSet contentType="audio">',
                          '<AdaptationSet contentType="audio">'
                          '<ContentProtection schemeIdUri="urn:mpeg:dash:mp4protection:2011" value="cenc"/>')
    uri = 'data:application/dash+xml;base64,' + base64.b64encode(mpd.encode()).decode()
    formats = ['FLAC_HIRES'] if protected else ['FLAC']
    return response(payload={'data': {'attributes': {'formats': formats, 'uri': uri}}})


class PlaybackClientTests(unittest.TestCase):
    def setUp(self):
        self.api = TidalAPI()
        self.addCleanup(self.api.session.close)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.token = TokenSettings()
        self.token.read(str(Path(self.directory.name) / 'token.json'))
        self.token.accessToken = self.api.key.accessToken = 'private-access'
        self.token.refreshToken = self.api.key.refreshToken = 'private-refresh'
        self.token.userid = self.api.key.userId = 'test-user'
        self.token.countryCode = self.api.key.countryCode = 'US'
        self.token.clientId = self.api.apiKey['clientId']
        self.token.expiresAfter = 9999999999
        self.token.save()
        self.saved = Path(self.token._path_).read_bytes()
        for patcher in (
            mock.patch('tidal_dl.tidal.TOKEN', self.token),
            mock.patch.object(SETTINGS, 'downloadDelay', False),
            mock.patch.object(SETTINGS, 'adaptiveRateLimit', False),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def assertSessionKept(self):
        self.assertEqual(self.api.key.accessToken, 'private-access')
        self.assertEqual(self.token.refreshToken, 'private-refresh')
        self.assertEqual(Path(self.token._path_).read_bytes(), self.saved)

    def test_playback_4022_preserves_session_without_refreshing(self):
        denied = response(404, {
            'subStatus': 4022, 'userMessage': 'private-access private-refresh',
            'client_secret': self.api.apiKey['clientSecret'],
        })
        with mock.patch.object(self.api.session, 'get', return_value=denied) as get, \
                mock.patch.object(self.api, '__refreshSavedAccessToken__') as refresh:
            with self.assertRaises(TidalApiError) as error:
                self.api.__getPlaybackData__(465909959, {'audioquality': 'LOSSLESS'})
        self.assertSessionKept()
        refresh.assert_not_called()
        get.assert_called_once()
        denied.close.assert_called()
        self.assertIn('4022', error.exception.errorCodes)
        message = str(error.exception)
        for detail in (self.api.apiKey['platform'], 'US', 'LOSSLESS', 'playbackinfopostpaywall', 'kept'):
            self.assertIn(detail, message)
        for secret in ('private-access', 'private-refresh', self.api.apiKey['clientSecret']):
            self.assertNotIn(secret, message)
        self.assertNotIn('log out', download.__downloadErrorHint__(error.exception))
        self.assertNotIn('log out', download.__downloadErrorHint__(message))

    def test_track_id_containing_429_is_not_misdiagnosed_as_a_rate_limit(self):
        with mock.patch.object(self.api.session, 'get', side_effect=[rejected(), openapi()]):
            stream = self.api.getStreamUrlByPriority(1429123, [AudioQuality.HiFi])
        self.assertEqual(stream.soundQuality, 'LOSSLESS')
        error = self.api.__playbackClientError__('tracks/1429123/playbackinfopostpaywall', 'LOSSLESS')
        self.assertIn('login kept', download.__downloadErrorHint__(error))
        self.assertSessionKept()

    def test_playback_4022_can_recover_via_openapi(self):
        with mock.patch.object(self.api.session, 'get', side_effect=[rejected(), openapi()]) as get:
            stream = self.api.getStreamUrlByPriority(465909959, [AudioQuality.HiFi])
        self.assertEqual(stream.soundQuality, 'LOSSLESS')
        self.assertEqual(len(stream.urls), 3)
        self.assertEqual(get.call_count, 2)
        self.assertIn('openapi.tidal.com', get.call_args_list[1].args[0])
        self.assertSessionKept()
        self.assertNotIn('LOSSLESS', self.api._playbackBlockedParams)

    def test_both_playback_endpoints_4022_allow_next_configured_quality(self):
        with mock.patch.object(self.api.session, 'get', side_effect=[
            rejected(), rejected(), playback(),
        ]) as get:
            stream = self.api.getStreamUrlByPriority(465909959, [AudioQuality.Max, AudioQuality.HiFi])
        self.assertEqual(stream.soundQuality, 'LOSSLESS')
        self.assertEqual(stream.fallbackQuality, 'HiFi')
        self.assertEqual(get.call_count, 3)
        self.assertSessionKept()

    def test_exhausted_playback_attempts_keep_session_and_actionable_error(self):
        with mock.patch.object(self.api.session, 'get', side_effect=[rejected(), rejected()]) as get:
            with self.assertRaises(TidalApiError) as error:
                self.api.getStreamUrlByPriority(465909959, [AudioQuality.HiFi])
        self.assertEqual(get.call_count, 2)
        self.assertSessionKept()
        self.assertIn('trackManifests', str(error.exception))
        self.assertIn('FLAC', str(error.exception))
        self.assertIn('kept', str(error.exception))
        self.assertNotIn('stale', download.__downloadErrorHint__(error.exception))

    def test_openapi_jsonapi_4022_is_a_playback_rejection(self):
        denied = response(404, {'errors': [{'status': '404', 'code': '4022'}]})
        with mock.patch.object(self.api.session, 'get', return_value=denied) as get:
            with self.assertRaises(TidalApiError) as error:
                self.api.__getOpenApiTrackManifest__(465909959, ['FLAC_HIRES', 'FLAC'])
        get.assert_called_once()
        self.assertIn('kept', str(error.exception))
        self.assertSessionKept()

    def test_catalog_4022_still_clears_unusable_session_without_legacy_retry(self):
        with mock.patch.object(self.api.session, 'get', return_value=rejected()) as get, \
                mock.patch.object(self.api, '__refreshSavedAccessToken__', return_value=False):
            with self.assertRaises(TidalApiError):
                self.api.getTrack(465909959)
        self.assertIsNone(self.api.key.accessToken)
        saved = TokenSettings()
        saved.read(self.token._path_)
        self.assertIsNone(saved.accessToken)
        get.assert_called_once()

    def test_video_playback_rejection_keeps_session(self):
        with mock.patch.object(self.api.session, 'get', return_value=rejected()):
            with self.assertRaises(TidalApiError):
                self.api.__getPlaybackData__(123, {'videoquality': 'HIGH'}, media='videos')
        self.assertSessionKept()

    def test_rate_limit_after_4022_is_not_hidden_by_quality_fallback(self):
        limited = response(429)
        with mock.patch.object(self.api.session, 'get', side_effect=[rejected(), limited]) as get, \
                mock.patch('tidal_dl.tidal.RateLimitWaitBudget.allows', return_value=False):
            with self.assertRaises(TidalApiError) as error:
                self.api.getStreamUrlByPriority(465909959, [AudioQuality.Max, AudioQuality.HiFi])
        self.assertEqual(error.exception.statusCode, 429)
        self.assertEqual(get.call_count, 2)
        self.assertSessionKept()

    def test_legacy_master_download_uses_modern_lossless_and_preserves_setting(self):
        with mock.patch.object(download, 'TIDAL_API', self.api), \
                mock.patch.object(SETTINGS, 'audioQuality', AudioQuality.Master), \
                mock.patch.object(SETTINGS, 'audioQualityPriority', []), \
                mock.patch.object(self.api.session, 'get', return_value=playback('HI_RES_LOSSLESS')) as get:
            stream = download.__getTrackStream__(465909959)
            self.assertEqual(SETTINGS.audioQuality, AudioQuality.Master)
        self.assertEqual(stream.soundQuality, 'HI_RES_LOSSLESS')
        self.assertEqual(stream.requestedQuality, 'Master')
        self.assertEqual(stream.fallbackQuality, 'Max')
        get.assert_called_once()
        self.assertEqual(get.call_args.kwargs['params']['audioquality'], 'HI_RES_LOSSLESS')
        self.assertSessionKept()

    def test_legacy_master_can_use_cd_quality_flac(self):
        with mock.patch.object(self.api.session, 'get', side_effect=[rejected(), rejected(), playback()]) as get:
            stream = self.api.getStreamUrlByPriority(465909959, ['Master'])
        self.assertEqual(stream.soundQuality, 'LOSSLESS')
        self.assertEqual(stream.fallbackQuality, 'HiFi')
        self.assertEqual(get.call_count, 3)
        self.assertSessionKept()

    def test_legacy_master_does_not_silently_accept_aac(self):
        denied = response(403, {'errors': [{'code': 'CLIENT_NOT_ENTITLED'}]})
        with mock.patch.object(self.api.session, 'get', side_effect=[
            playback('HIGH'), denied, playback('HIGH'), denied,
        ]) as get:
            with self.assertRaises(TidalStreamUnavailable):
                self.api.getStreamUrlByPriority(465909959, [AudioQuality.Master])
        self.assertEqual(get.call_count, 4)
        self.assertSessionKept()

    def test_explicit_priority_order_is_preserved_when_master_is_replaced(self):
        with mock.patch.object(self.api.session, 'get', side_effect=[
            rejected(), rejected(), playback('HIGH'),
        ]) as get:
            stream = self.api.getStreamUrlByPriority(465909959, [AudioQuality.Master, AudioQuality.High,
                                                               AudioQuality.HiFi])
        self.assertEqual(stream.soundQuality, 'HIGH')
        self.assertEqual(get.call_args.kwargs['params']['audioquality'], 'HIGH')
        self.assertSessionKept()

    def test_cancellation_during_playback_rejection_stops_fallback(self):
        cancel = threading.Event()

        def reject_then_cancel(*args, **kwargs):
            cancel.set()
            return rejected()

        with job_context(cancel=cancel), \
                mock.patch.object(self.api.session, 'get', side_effect=reject_then_cancel) as get:
            with self.assertRaises(DownloadCancelled):
                self.api.getStreamUrlByPriority(465909959, [AudioQuality.Max, AudioQuality.HiFi])
        get.assert_called_once()
        self.assertSessionKept()

    def test_master_cache_does_not_change_strict_max_request(self):
        with mock.patch.object(self.api.session, 'get', return_value=playback('HI_RES_LOSSLESS')) as get:
            master = self.api.getStreamUrlByPriority(465909959, [AudioQuality.Master])
            maximum = self.api.getStreamUrlByPriority(465909959, [AudioQuality.Max])
            cached = self.api.getStreamUrlByPriority(465909959, [AudioQuality.Master])
        self.assertEqual(get.call_count, 2)
        self.assertEqual(master.requestedQuality, cached.requestedQuality)
        self.assertEqual(maximum.requestedQuality, 'Max')
        self.assertIsNone(maximum.fallbackQuality)

    def test_live_case_protected_hires_uses_available_clear_lossless(self):
        with mock.patch.object(self.api.session, 'get', side_effect=[
            playback(), openapi(protected=True), playback(),
        ]) as get:
            stream = self.api.getStreamUrlByPriority(465909959, [AudioQuality.Master])
        self.assertEqual(stream.soundQuality, 'LOSSLESS')
        self.assertEqual(stream.fallbackQuality, 'HiFi')
        self.assertEqual(stream.url, 'https://audio.example/track.flac')
        self.assertEqual(get.call_count, 3)
        self.assertSessionKept()

    def test_protected_only_response_is_not_returned_or_cached_as_playable(self):
        with mock.patch.object(self.api.session, 'get', side_effect=[rejected(), openapi(protected=True)]) as get:
            with self.assertRaisesRegex(TidalStreamUnavailable, 'DRM-protected'):
                self.api.getStreamUrlByPriority(465909959, [AudioQuality.Max])
        self.assertEqual(get.call_count, 2)
        self.assertFalse(self.api._streamCache)
        self.assertSessionKept()

    def test_protection_at_any_dash_level_is_rejected_before_url_extraction(self):
        from xml.etree import ElementTree
        manifest = base64.b64decode(openapi().json()['data']['attributes']['uri'].split(',', 1)[1])
        for tag in ('MPD', 'Period', 'AdaptationSet', 'Representation'):
            with self.subTest(tag=tag):
                root = ElementTree.fromstring(manifest)
                parent = next(node for node in root.iter() if node.tag.rsplit('}', 1)[-1] == tag)
                ElementTree.SubElement(parent, '{urn:mpeg:dash:schema:mpd:2011}ContentProtection',
                                       {'schemeIdUri': 'urn:mpeg:dash:mp4protection:2011', 'value': 'cenc'})
                with self.assertRaisesRegex(TidalStreamUnavailable, 'DRM-protected'):
                    self.api.parse_mpd(ElementTree.tostring(root))

    def test_real_http_login_fallback_download_tagging_and_retry(self):
        # A tiny FLAC of generated silence, not a copyrighted track. The server
        # models a US login accepted by auth but rejected for hi-res playback.
        media = base64.b64decode(
            'ZkxhQwAAACICQAJAAAAAAASVAfQA8AAAAAAAAAAAAAAAAAAAAAAAAAAABAAADgYAAABmZm1wZWcAAAAAgQAAAP/4ZAgAnzcAAABBLQ=='
        )
        calls = []
        artist = {'id': 1, 'name': 'Fixture artist'}
        album = {'id': 2, 'title': 'Fixture album', 'artist': artist, 'artists': [artist],
                 'releaseDate': '2026-09-17', 'numberOfVolumes': 1, 'numberOfTracks': 1}
        track = {'id': 465909959, 'title': 'Issue 65 fixture', 'album': album,
                 'artist': artist, 'artists': [artist], 'trackNumber': 1, 'volumeNumber': 1,
                 'allowStreaming': True, 'streamReady': True, 'audioQuality': 'LOSSLESS'}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def send_payload(self, payload, status=200):
                content = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                self.send_response(status)
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)

            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                calls.append(self.path)
                if self.path.endswith('/device_authorization'):
                    self.send_payload({'deviceCode': 'test-device', 'userCode': 'test-code',
                                       'verificationUri': 'login.example.invalid', 'expiresIn': 300, 'interval': 1})
                elif self.path.endswith('/token'):
                    self.send_payload({'user': {'userId': 'test-user', 'countryCode': 'US'},
                                       'access_token': 'private-access', 'refresh_token': 'private-refresh',
                                       'expires_in': 14400})
                else:
                    self.send_payload({}, 404)

            def do_GET(self):
                calls.append(self.path)
                parsed = urlsplit(self.path)
                if parsed.path == '/audio.flac':
                    self.send_payload(media)
                elif self.headers.get('Authorization') != 'Bearer private-access':
                    self.send_payload({}, 401)
                elif parsed.path.endswith('/sessions'):
                    self.send_payload({'userId': 'test-user', 'countryCode': 'US'})
                elif parsed.path.endswith('/contributors'):
                    self.send_payload({'items': []})
                elif 'trackManifests' in parsed.path or 'playbackinfo' in parsed.path:
                    quality = parse_qs(parsed.query).get('audioquality', [''])[0]
                    if quality != 'LOSSLESS':
                        self.send_payload(rejected().json(), 404)
                    else:
                        payload = playback().json()
                        payload['manifest'] = base64.b64encode(json.dumps({
                            'codecs': 'flac', 'mimeType': 'audio/flac',
                            'urls': [base_url + '/audio.flac'],
                        }).encode()).decode()
                        self.send_payload(payload)
                elif parsed.path.endswith('/tracks/465909959'):
                    self.send_payload(track)
                else:
                    self.send_payload({}, 404)

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f'http://127.0.0.1:{server.server_address[1]}'
        original_request = self.api.session.request

        def local_request(method, url, **kwargs):
            self.assertIn(urlsplit(url).hostname, ('api.tidal.com', 'api.tidalhifi.com',
                                                 'openapi.tidal.com', 'auth.tidal.com'))
            return original_request(method, base_url + urlsplit(url).path, **kwargs)

        try:
            with mock.patch.object(self.api.session, 'request', side_effect=local_request), \
                    mock.patch.object(events, 'TIDAL_API', self.api), \
                    mock.patch.object(events, 'TOKEN', self.token), \
                    mock.patch.object(download, 'TIDAL_API', self.api), \
                    mock.patch.object(paths, 'TIDAL_API', self.api), \
                    mock.patch.multiple(SETTINGS, audioQuality=AudioQuality.Master, audioQualityPriority=[],
                                        downloadPath=self.directory.name, albumFolderFormat='album',
                                        trackFileFormat='{TrackTitle}', lyricFile=False, saveAsFlac=False,
                                        showTrackInfo=False, showProgress=False, multiThread=False, checkExist=True):
                self.api.clearSession()
                self.assertTrue(events.loginByWeb())
                self.saved = Path(self.token._path_).read_bytes()
                downloaded_track = self.api.getTrack(465909959)
                ok, message = download.downloadTrack(downloaded_track, downloaded_track.album)
                self.assertTrue(ok, message)
                files = list(Path(self.directory.name).rglob('*.flac'))
                self.assertEqual(len(files), 1)
                self.assertEqual(FLAC(files[0])['title'], ['Issue 65 fixture'])
                receipt = json.loads(Path(str(files[0]) + '.tidekeeper.json').read_text())
                self.assertTrue(receipt['metadata_complete'])
                self.assertEqual(receipt['identity']['quality'], 'LOSSLESS')
                self.assertTrue(self.api.verifyAccessToken(self.token.accessToken))
                self.assertSessionKept()
                self.assertTrue(download.downloadTrack(downloaded_track, downloaded_track.album)[0])
                self.assertEqual(calls.count('/audio.flac'), 1)
                self.assertEqual(sum('playbackinfo' in call for call in calls), 2)
                self.assertFalse(any('audioquality=HI_RES&' in call for call in calls))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
