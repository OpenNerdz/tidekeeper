import base64
import json
import unittest
from unittest import mock

from tidal_dl.enums import (
    AUDIO_QUALITY_ORDER,
    AudioQuality,
    audio_quality_fallbacks,
    playback_quality_priority,
)
from tidal_dl.settings import Settings, getDefaultAudioQualityPriority
from tidal_dl.tidal import TidalAPI, TidalApiError

from fixtures import CatalogFixtures, playback_params


class QualityPolicyTests(unittest.TestCase):
    def test_modern_fallbacks_share_one_order_without_master(self):
        self.assertNotIn(AudioQuality.Master, AUDIO_QUALITY_ORDER)
        for index, quality in enumerate(AUDIO_QUALITY_ORDER):
            self.assertEqual(audio_quality_fallbacks(quality), list(AUDIO_QUALITY_ORDER[index:]))
        self.assertEqual(getDefaultAudioQualityPriority(), audio_quality_fallbacks(AudioQuality.Max))

    def test_legacy_priority_is_lossless_and_explicit_order_is_preserved(self):
        cases = [
            ([], []),
            ([AudioQuality.Master], [AudioQuality.Max, AudioQuality.HiFi]),
            ([AudioQuality.Max], [AudioQuality.Max]),
            ([AudioQuality.High, AudioQuality.Master, AudioQuality.Max], [AudioQuality.High, AudioQuality.Max]),
        ]
        for saved, expected in cases:
            with self.subTest(saved=saved):
                self.assertEqual(playback_quality_priority(iter(saved)), expected)

    def test_selected_quality_leads_stale_saved_fallbacks(self):
        settings = Settings()
        settings.audioQuality = AudioQuality.Max
        settings.audioQualityPriority = [
            AudioQuality.HiFi, AudioQuality.High, AudioQuality.Normal, AudioQuality.Atmos,
        ]

        self.assertEqual(settings.getDownloadAudioQualityPriority(), [
            AudioQuality.Max, AudioQuality.HiFi, AudioQuality.High,
            AudioQuality.Normal, AudioQuality.Atmos,
        ])


class QualityFallbackTests(CatalogFixtures, unittest.TestCase):
    def test_atmos_client_not_entitled_falls_back_to_max_stream(self):
        api = TidalAPI()
        manifest = base64.b64encode(json.dumps({
            "codecs": "flac",
            "urls": ["https://example.invalid/fallback.flac"],
            "mimeType": "audio/flac",
        }).encode("utf-8")).decode("utf-8")

        with mock.patch.object(
            api,
            "_getOpenApiTrackManifest",
            side_effect=Exception(
                'Track manifest request failed: HTTP 403 {"errors":[{"code":"CLIENT_NOT_ENTITLED"}]}'
            ),
        ), mock.patch.object(api, "_getPlaybackData", return_value={
            "trackid": 456,
            "audioQuality": "HI_RES_LOSSLESS",
            "manifestMimeType": "application/vnd.tidal.bt",
            "manifest": manifest,
        }) as fallback_get:
            stream = api.getStreamUrl(456, AudioQuality.Atmos)

        self.assertEqual(stream.soundQuality, "HI_RES_LOSSLESS")
        self.assertEqual(stream.url, "https://example.invalid/fallback.flac")
        fallback_get.assert_called_once_with(456, playback_params("HI_RES_LOSSLESS"))

    def test_blocked_max_stream_falls_back_to_hifi_without_retired_mqa(self):
        api = TidalAPI()
        manifest = base64.b64encode(json.dumps({
            "codecs": "flac",
            "urls": ["https://example.invalid/hires.flac"],
            "mimeType": "audio/flac",
        }).encode("utf-8")).decode("utf-8")

        blocked = TidalApiError(
            'Get operation failed: HTTP 403 {"errors":[{"code":"CLIENT_NOT_ENTITLED"}]}',
            403,
            ["CLIENT_NOT_ENTITLED"],
        )

        with mock.patch.object(api, "_getOpenApiTrackManifest", side_effect=blocked), \
             mock.patch.object(api, "_getPlaybackData", side_effect=[
                blocked,
                {
                    "trackid": 456,
                    "audioQuality": "LOSSLESS",
                    "manifestMimeType": "application/vnd.tidal.bt",
                    "manifest": manifest,
                },
            ]) as get:
            stream = api.getStreamUrl(456, AudioQuality.Max)

        self.assertEqual(stream.soundQuality, "LOSSLESS")
        self.assertEqual(stream.url, "https://example.invalid/hires.flac")
        self.assertEqual(stream.requestedQuality, "Max")
        self.assertEqual(stream.fallbackQuality, "HiFi")
        self.assertEqual(stream.fallbackReason, "requested format is not allowed for this account or track")
        self.assertIn("CLIENT_NOT_ENTITLED", stream.fallbackError)
        self.assertEqual(
            get.call_args_list,
            [
                mock.call(456, playback_params("HI_RES_LOSSLESS")),
                mock.call(456, playback_params("LOSSLESS")),
            ],
        )

    def test_standard_api_quality_mismatch_falls_through_to_openapi_flac(self):
        """Issue #32: standard playback API returns HIGH when LOSSLESS was
        requested.  The OpenAPI FLAC endpoint should be tried before giving up."""
        api = TidalAPI()

        # Standard playback API returns HIGH (wrong quality).
        high_manifest = base64.b64encode(json.dumps({
            "codecs": "aac",
            "urls": ["https://example.invalid/high.m4a"],
            "mimeType": "audio/mp4",
        }).encode("utf-8")).decode("utf-8")

        # OpenAPI FLAC endpoint returns LOSSLESS (correct quality).
        flac_xml = self._dash_manifest("flac")
        flac_uri = "data:application/dash+xml;base64," + base64.b64encode(
            flac_xml.encode("utf-8")
        ).decode("utf-8")

        with mock.patch.object(api, "_getPlaybackData", return_value={
            "trackid": 456,
            "audioQuality": "HIGH",
            "manifestMimeType": "application/vnd.tidal.bt",
            "manifest": high_manifest,
        }), mock.patch.object(api, "_getOpenApiTrackManifest", return_value={
            "formats": ["FLAC"],
            "uri": flac_uri,
        }) as openapi_get:
            stream = api.getStreamUrlByPriority(456, [AudioQuality.HiFi])

        self.assertEqual(stream.soundQuality, "LOSSLESS")
        self.assertIn("flac", stream.codec.lower())
        openapi_get.assert_called_once()

    def test_audio_quality_priority_tries_high_before_lossless(self):
        api = TidalAPI()
        manifest = base64.b64encode(json.dumps({
            "codecs": "aac",
            "urls": ["https://example.invalid/fallback.m4a"],
            "mimeType": "audio/mp4",
        }).encode("utf-8")).decode("utf-8")

        with mock.patch.object(
            api,
            "_getOpenApiTrackManifest",
            side_effect=Exception(
                'Track manifest request failed: HTTP 403 {"errors":[{"code":"CLIENT_NOT_ENTITLED"}]}'
            ),
        ), mock.patch.object(api, "_getPlaybackData", return_value={
            "trackid": 456,
            "audioQuality": "HIGH",
            "manifestMimeType": "application/vnd.tidal.bt",
            "manifest": manifest,
        }) as fallback_get:
            stream = api.getStreamUrlByPriority(456, [
                "Atmos",
                "High",
                "HiFi",
                "Normal",
            ])

        self.assertEqual(stream.soundQuality, "HIGH")
        self.assertEqual(stream.url, "https://example.invalid/fallback.m4a")
        fallback_get.assert_any_call(456, playback_params("HIGH"))

    def test_audio_quality_priority_rejects_lower_actual_quality_and_keeps_trying(self):
        api = TidalAPI()
        low_manifest = base64.b64encode(json.dumps({
            "codecs": "aac",
            "urls": ["https://example.invalid/low.m4a"],
            "mimeType": "audio/mp4",
        }).encode("utf-8")).decode("utf-8")
        lossless_uri = "data:application/dash+xml;base64," + base64.b64encode(
            self._dash_manifest("flac").encode("utf-8")
        ).decode("utf-8")

        with mock.patch.object(
            api,
            "_getOpenApiTrackManifest",
            side_effect=[
                Exception(
                    'Track manifest request failed: HTTP 403 {"errors":[{"code":"CLIENT_NOT_ENTITLED"}]}'
                ),
                {
                    "formats": ["FLAC"],
                    "uri": lossless_uri,
                },
            ],
        ), mock.patch.object(api, "_getPlaybackData", side_effect=[
            {
                "trackid": 456,
                "audioQuality": "LOW",
                "manifestMimeType": "application/vnd.tidal.bt",
                "manifest": low_manifest,
            },
            {
                "trackid": 456,
                "audioQuality": "LOW",
                "manifestMimeType": "application/vnd.tidal.bt",
                "manifest": low_manifest,
            },
        ]) as fallback_get:
            stream = api.getStreamUrlByPriority(456, [
                "Atmos",
                "High",
                "Lossless",
                "Low",
            ])

        self.assertEqual(stream.soundQuality, "LOSSLESS")
        self.assertEqual(stream.url, "https://example.invalid/init.mp4")
        self.assertEqual(stream.requestedQuality, "Dolby Atmos")
        self.assertEqual(stream.fallbackQuality, "HiFi")
        fallback_get.assert_any_call(456, playback_params("HIGH"))

if __name__ == '__main__':
    unittest.main()
