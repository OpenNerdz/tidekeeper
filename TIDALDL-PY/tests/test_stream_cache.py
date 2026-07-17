import unittest
from types import SimpleNamespace
from unittest import mock

from tidal_dl.enums import AudioQuality
from tidal_dl.tidal import STREAM_CACHE_TTL_SECONDS, TidalAPI


class StreamCacheTests(unittest.TestCase):
    def _stream(self):
        return SimpleNamespace(
            soundQuality="LOSSLESS",
            requestedQuality=None,
            fallbackQuality=None,
            fallbackReason=None,
            fallbackError=None,
            urls=["https://media.example/track"],
        )

    def test_duplicate_track_resolution_uses_short_lived_cache(self):
        api = TidalAPI()
        stream = self._stream()
        with mock.patch.object(api, "__getAudioStreamUrlForQuality__", return_value=stream) as resolve:
            first = api.getStreamUrlByPriority(123, [AudioQuality.HiFi])
            second = api.getStreamUrlByPriority(123, [AudioQuality.HiFi])

        self.assertEqual(resolve.call_count, 1)
        self.assertEqual(second.urls, first.urls)
        self.assertIsNot(second, first)

    def test_callers_cannot_mutate_cached_stream(self):
        api = TidalAPI()
        with mock.patch.object(api, "__getAudioStreamUrlForQuality__", return_value=self._stream()):
            first = api.getStreamUrlByPriority(123, [AudioQuality.HiFi])
            first.urls.append("corrupt")
            second = api.getStreamUrlByPriority(123, [AudioQuality.HiFi])

        self.assertEqual(second.urls, ["https://media.example/track"])

    def test_expired_stream_is_resolved_again(self):
        api = TidalAPI()
        with mock.patch.object(api, "__getAudioStreamUrlForQuality__", return_value=self._stream()) as resolve, \
             mock.patch("tidal_dl.tidal.time.monotonic", side_effect=[0.0, 0.0, STREAM_CACHE_TTL_SECONDS + 1, STREAM_CACHE_TTL_SECONDS + 1]):
            api.getStreamUrlByPriority(123, [AudioQuality.HiFi])
            api.getStreamUrlByPriority(123, [AudioQuality.HiFi])

        self.assertEqual(resolve.call_count, 2)

    def test_get_stream_url_shares_priority_cache(self):
        api = TidalAPI()
        stream = self._stream()
        with mock.patch.object(api, "__getAudioStreamUrlForQuality__", return_value=stream) as resolve:
            first = api.getStreamUrl(123, AudioQuality.HiFi)
            second = api.getStreamUrlByPriority(123, api.__qualityFallbacks__(AudioQuality.HiFi))

        self.assertEqual(resolve.call_count, 1)
        self.assertEqual(second.urls, first.urls)

    def test_stream_cache_ttl_is_short_lived(self):
        # Signed CDN URLs often expire in minutes; keep the cache brief.
        self.assertLessEqual(STREAM_CACHE_TTL_SECONDS, 120)


if __name__ == "__main__":
    unittest.main()
