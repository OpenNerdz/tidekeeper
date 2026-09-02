import unittest
from types import SimpleNamespace
from unittest import mock

from tidal_dl.tidal import API_BASE_PRIMARY, TidalAPI, TidalApiError


class RateLimitWaitCapTests(unittest.TestCase):
    def test_catalog_429_retries_beyond_three_until_success(self):
        api = TidalAPI()
        limited = SimpleNamespace(
            status_code=429,
            text="rate limited",
            headers={"Retry-After": "1"},
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
        with mock.patch.object(api.session, "get", side_effect=[limited, limited, limited, limited, success]) as get, \
             mock.patch.object(api, "__applyRateLimitPenalty__", return_value=1.0), \
             mock.patch("tidal_dl.tidal.time.sleep") as sleep, \
             mock.patch("builtins.print"):
            result = api.__getOnce__("albums/1", urlpre=API_BASE_PRIMARY)
        self.assertEqual(result, {"id": 1})
        self.assertEqual(get.call_count, 5)
        self.assertEqual(sleep.call_count, 4)

    def test_catalog_429_gives_up_after_wait_cap(self):
        api = TidalAPI()
        limited = SimpleNamespace(
            status_code=429,
            text="rate limited",
            headers={"Retry-After": "60"},
            close=mock.Mock(),
            json=mock.Mock(return_value={}),
        )
        with mock.patch.object(api.session, "get", return_value=limited), \
             mock.patch.object(api, "__applyRateLimitPenalty__", return_value=60.0), \
             mock.patch("tidal_dl.tidal.time.sleep") as sleep, \
             mock.patch("builtins.print"):
            with self.assertRaises(TidalApiError) as raised:
                api.__getOnce__("albums/1", urlpre=API_BASE_PRIMARY)
        self.assertEqual(raised.exception.statusCode, 429)
        # First 429 waits 60s (under 90s cap); second 60s would exceed the cap.
        self.assertEqual(sleep.call_count, 1)

    def test_openapi_manifest_429_retries_beyond_three(self):
        api = TidalAPI()
        limited = SimpleNamespace(
            status_code=429,
            text="rate limited",
            headers={"Retry-After": "1"},
            close=mock.Mock(),
            json=mock.Mock(return_value={}),
        )
        success = SimpleNamespace(
            status_code=200,
            text='{"data":{"attributes":{"manifest":"ok"}}}',
            headers={},
            close=mock.Mock(),
            json=mock.Mock(return_value={"data": {"attributes": {"manifest": "ok"}}}),
        )
        with mock.patch.object(api.session, "get", side_effect=[limited, limited, limited, limited, success]) as get, \
             mock.patch.object(api, "__applyRateLimitPenalty__", return_value=1.0), \
             mock.patch.object(api, "__waitForStreamRequestQuota__"), \
             mock.patch("tidal_dl.tidal.time.sleep") as sleep, \
             mock.patch("builtins.print"):
            result = api.__getOpenApiTrackManifestOnce__(1, ["FLAC"], "DOWNLOAD")
        self.assertEqual(result, {"manifest": "ok"})
        self.assertEqual(get.call_count, 5)
        self.assertEqual(sleep.call_count, 4)


if __name__ == "__main__":
    unittest.main()
