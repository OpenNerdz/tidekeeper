import unittest
from unittest import mock

from tidal_dl.tidal import RequestRateLimiter


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


if __name__ == "__main__":
    unittest.main()
