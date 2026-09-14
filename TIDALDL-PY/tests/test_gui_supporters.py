import unittest
from unittest import mock

import requests

from tidal_dl.gui_app import supporters


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class SupporterListTests(unittest.TestCase):
    def test_remote_list_is_validated_and_deduplicated(self):
        response = _Response(["Alice", "bob-dev", "alice", "../bad", None])
        with mock.patch.object(supporters.requests, "get", return_value=response):
            names = supporters.load_supporters()
        self.assertEqual(names, ["Alice", "bob-dev"])

    def test_bundled_snapshot_is_used_offline(self):
        with mock.patch.object(
            supporters.requests,
            "get",
            side_effect=requests.ConnectionError("offline"),
        ):
            names = supporters.load_supporters()
        self.assertIn("Notorious2Beat", names)
        self.assertGreater(len(names), 50)

    def test_request_is_bounded_and_identifies_the_app(self):
        response = _Response([])
        with mock.patch.object(supporters.requests, "get", return_value=response) as get:
            supporters.load_supporters()
        _, kwargs = get.call_args
        self.assertEqual(kwargs["timeout"], (3, 8))
        self.assertEqual(kwargs["headers"]["User-Agent"], "Tidekeeper")


if __name__ == "__main__":
    unittest.main()
