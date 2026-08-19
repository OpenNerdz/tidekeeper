import unittest
from types import SimpleNamespace
from unittest import mock

from tidal_dl.enums import AudioQuality
from tidal_dl.tidal import (
    API_BASE_PRIMARY,
    RequestRateLimiter,
    TidalAPI,
    TidalApiError,
    TidalStreamUnavailable,
)


class AdaptiveRateLimiterTests(unittest.TestCase):
    def test_penalty_raises_effective_interval(self):
        limiter = RequestRateLimiter(minInterval=3.0, jitter=0.0)

        with mock.patch("tidal_dl.tidal.time.monotonic", return_value=100.0):
            interval = limiter.penalize(12.0)

        self.assertEqual(interval, 12.0)
        self.assertEqual(limiter.effectiveInterval(), 12.0)

    def test_successes_gradually_restore_configured_interval(self):
        limiter = RequestRateLimiter(minInterval=3.0, jitter=0.0)
        with mock.patch("tidal_dl.tidal.time.monotonic", return_value=100.0):
            limiter.penalize(12.0)

        for _ in range(5):
            limiter.reward()

        self.assertAlmostEqual(limiter.effectiveInterval(), 9.6)

    def test_wait_uses_adaptive_interval(self):
        limiter = RequestRateLimiter(minInterval=1.0, jitter=0.0)
        with mock.patch("tidal_dl.tidal.time.monotonic", return_value=100.0):
            limiter.penalize(8.0)

        with mock.patch("tidal_dl.tidal.time.monotonic", return_value=101.0), \
             mock.patch("tidal_dl.tidal.time.sleep") as sleep:
            delay = limiter.wait()

        self.assertEqual(delay, 7.0)
        sleep.assert_called_once_with(7.0)

    def test_client_not_entitled_is_not_retryable_manifest_error(self):
        api = TidalAPI()
        error = TidalApiError("blocked", 403, ["CLIENT_NOT_ENTITLED"])
        self.assertFalse(api.__isRetryableManifestError__(error))
        self.assertTrue(api.__isRetryableManifestError__(
            TidalApiError("missing", 403, ["PREREQUISITE_MISSING"])
        ))

    def test_openapi_client_not_entitled_does_not_retry_playback_usage(self):
        api = TidalAPI()
        error = TidalApiError("blocked", 403, ["CLIENT_NOT_ENTITLED"])
        with mock.patch.object(api, "__getOpenApiTrackManifestOnce__", side_effect=error) as once:
            with self.assertRaises(TidalApiError):
                api.__getOpenApiTrackManifest__(123, ["EAC3_JOC"])
        once.assert_called_once()
        self.assertEqual(once.call_args.args[2], "DOWNLOAD")

    def test_atmos_miss_is_cached_for_session(self):
        api = TidalAPI()
        with mock.patch.object(
            api,
            "__getOpenApiTrackManifest__",
            side_effect=TidalApiError("blocked", 403, ["CLIENT_NOT_ENTITLED"]),
        ) as openapi:
            with self.assertRaises(TidalApiError):
                api.__getAtmosStreamUrl__(999)
            with self.assertRaises(TidalStreamUnavailable):
                api.__getAtmosStreamUrl__(999)
        openapi.assert_called_once()
        self.assertIn("999", api._atmosUnavailableTrackIds)

    def test_atmos_transient_403_is_not_cached(self):
        api = TidalAPI()
        with mock.patch.object(
            api,
            "__getOpenApiTrackManifest__",
            side_effect=TidalApiError("cdn blip", 403, []),
        ) as openapi:
            with self.assertRaises(TidalApiError):
                api.__getAtmosStreamUrl__(888)
            with self.assertRaises(TidalApiError):
                api.__getAtmosStreamUrl__(888)
        self.assertEqual(openapi.call_count, 2)
        self.assertNotIn("888", api._atmosUnavailableTrackIds)

    def test_atmos_only_quality_does_not_probe_standard_hi_res(self):
        api = TidalAPI()
        with mock.patch.object(
            api,
            "__getAtmosStreamUrl__",
            side_effect=TidalStreamUnavailable("no atmos"),
        ), mock.patch.object(api, "__getStandardStreamUrl__") as standard:
            with self.assertRaises(TidalStreamUnavailable):
                api.__getAudioStreamUrlForQuality__(456, AudioQuality.Atmos)
        standard.assert_not_called()

    def test_catalog_429_applies_adaptive_penalty(self):
        api = TidalAPI()
        response = SimpleNamespace(
            status_code=429,
            text="rate limited",
            headers={"Retry-After": "11"},
            close=mock.Mock(),
            json=mock.Mock(return_value={}),
        )
        success = SimpleNamespace(
            status_code=200,
            text='{"id":1}',
            headers={},
            close=mock.Mock(),
            json=mock.Mock(return_value={"id": 1}),
        )
        with mock.patch.object(api.session, "get", side_effect=[response, success]), \
             mock.patch.object(api, "__applyRateLimitPenalty__", return_value=11.0) as penalize, \
             mock.patch("tidal_dl.tidal.time.sleep") as sleep, \
             mock.patch("builtins.print"):
            result = api.__getOnce__("albums/1", urlpre=API_BASE_PRIMARY)
        self.assertEqual(result, {"id": 1})
        penalize.assert_called_once()
        sleep.assert_called_once_with(11.0)

    def test_auth_post_closes_successful_response(self):
        api = TidalAPI()
        response = SimpleNamespace(
            status_code=200,
            text='{"access_token":"ok"}',
            headers={},
            close=mock.Mock(),
            json=mock.Mock(return_value={"access_token": "ok"}),
        )
        with mock.patch.object(api.session, "post", return_value=response):
            result = api.__post__("/token", {})
        self.assertEqual(result, {"access_token": "ok"})
        response.close.assert_called_once_with()

    def test_catalog_503_uses_bounded_backoff_before_retry(self):
        api = TidalAPI()
        failed = SimpleNamespace(
            status_code=503,
            text="unavailable",
            headers={"Retry-After": "4"},
            close=mock.Mock(),
            json=mock.Mock(return_value={}),
        )
        success = SimpleNamespace(
            status_code=200,
            text='{"id":1}',
            headers={},
            close=mock.Mock(),
            json=mock.Mock(return_value={"id": 1}),
        )
        with mock.patch.object(api.session, "get", side_effect=[failed, success]), \
             mock.patch("tidal_dl.tidal.time.sleep") as sleep:
            result = api.__getOnce__("albums/1", urlpre=API_BASE_PRIMARY)
        self.assertEqual(result, {"id": 1})
        sleep.assert_called_once_with(4.0)

    def test_catalog_rejects_non_object_json(self):
        api = TidalAPI()
        response = SimpleNamespace(
            status_code=200,
            text="[]",
            headers={},
            close=mock.Mock(),
            json=mock.Mock(return_value=[]),
        )
        with mock.patch.object(api.session, "get", return_value=response):
            with self.assertRaises(TidalApiError) as context:
                api.__getOnce__("albums/1", urlpre=API_BASE_PRIMARY)
        self.assertIn("invalid JSON payload", str(context.exception))

    def test_manifest_rejects_missing_attributes(self):
        api = TidalAPI()
        response = SimpleNamespace(
            status_code=200,
            text='{"data":{}}',
            headers={},
            close=mock.Mock(),
            json=mock.Mock(return_value={"data": {}}),
        )
        with mock.patch.object(api.session, "get", return_value=response), \
             mock.patch.object(api, "__waitForStreamRequestQuota__"):
            with self.assertRaises(TidalApiError) as context:
                api.__getOpenApiTrackManifestOnce__(1, ["FLAC"], "DOWNLOAD")
        self.assertIn("attributes are missing", str(context.exception))

    def test_atmos_album_twin_cache_avoids_repeat_lookup(self):
        api = TidalAPI()
        stereo = SimpleNamespace(
            id=100,
            title="Album",
            audioModes=["STEREO"],
            audioQuality="LOSSLESS",
            explicit=False,
            numberOfTracks=10,
            artist=SimpleNamespace(id=7, name="Artist"),
            artists=[SimpleNamespace(id=7, name="Artist")],
        )
        atmos = SimpleNamespace(
            id=200,
            title="Album",
            audioModes=["DOLBY_ATMOS"],
            audioQuality="LOW",
            explicit=False,
            numberOfTracks=10,
            artist=SimpleNamespace(id=7, name="Artist"),
            artists=[SimpleNamespace(id=7, name="Artist")],
        )
        with mock.patch.object(api, "getArtistAlbums", return_value=[stereo, atmos]) as albums:
            first = api.findAtmosAlbumVariant(stereo)
            second = api.findAtmosAlbumVariant(stereo)
        self.assertIs(first, atmos)
        self.assertIs(second, atmos)
        albums.assert_called_once()


if __name__ == "__main__":
    unittest.main()
