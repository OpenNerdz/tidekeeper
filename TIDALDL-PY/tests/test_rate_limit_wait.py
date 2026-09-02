import unittest
from types import SimpleNamespace
from unittest import mock

from tidal_dl.tidal import (
    API_BASE_PRIMARY,
    PLAYBACK_ASSET_NOT_READY_ATTEMPTS,
    RateLimitWaitBudget,
    TidalAPI,
    TidalApiError,
)


def _response(status_code, payload=None, text="", headers=None):
    payload = {} if payload is None else payload
    return SimpleNamespace(
        status_code=status_code,
        text=text,
        headers=headers or {},
        close=mock.Mock(),
        json=mock.Mock(return_value=payload),
    )


class RateLimitWaitBudgetTests(unittest.TestCase):
    def test_budget_allows_until_cap_is_reached(self):
        budget = RateLimitWaitBudget(maxWaitSeconds=10)
        self.assertTrue(budget.allows(6))
        budget.record(6)
        self.assertTrue(budget.allows(4))
        self.assertFalse(budget.allows(4.5))
        self.assertEqual(budget.attempts, 1)
        self.assertEqual(budget.waited, 6)


class ManifestAttemptBudgetTests(unittest.TestCase):
    def test_openapi_manifest_asset_not_ready_is_bounded(self):
        api = TidalAPI()
        not_ready = _response(401, {"subStatus": 4005, "userMessage": "Asset is not ready for playback"})
        with mock.patch.object(api.session, "get", return_value=not_ready) as get, \
             mock.patch.object(api, "__waitForStreamRequestQuota__"), \
             mock.patch("tidal_dl.tidal.time.sleep") as sleep, \
             mock.patch("builtins.print"):
            with self.assertRaises(TidalApiError) as raised:
                api.__getOpenApiTrackManifestOnce__(1, ["FLAC"], "DOWNLOAD")
        self.assertEqual(raised.exception.statusCode, 401)
        self.assertEqual(get.call_count, PLAYBACK_ASSET_NOT_READY_ATTEMPTS)
        self.assertEqual(sleep.call_count, PLAYBACK_ASSET_NOT_READY_ATTEMPTS)

    def test_openapi_manifest_429_does_not_consume_asset_attempts(self):
        api = TidalAPI()
        limited = _response(429, text="rate limited", headers={"Retry-After": "1"})
        not_ready = _response(401, {"subStatus": 4005, "userMessage": "Asset is not ready for playback"})
        success = _response(200, {"data": {"attributes": {"manifest": "ok"}}})
        # More 429s than the asset budget, then one asset wait, then success.
        responses = [limited] * (PLAYBACK_ASSET_NOT_READY_ATTEMPTS + 2) + [not_ready, success]
        with mock.patch.object(api.session, "get", side_effect=responses) as get, \
             mock.patch.object(api, "__applyRateLimitPenalty__", return_value=1.0), \
             mock.patch.object(api, "__waitForStreamRequestQuota__"), \
             mock.patch("tidal_dl.tidal.time.sleep"), \
             mock.patch("builtins.print"):
            result = api.__getOpenApiTrackManifestOnce__(1, ["FLAC"], "DOWNLOAD")
        self.assertEqual(result, {"manifest": "ok"})
        self.assertEqual(get.call_count, len(responses))


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
