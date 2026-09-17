import unittest

from tidal_dl import apiKey


class ApiKeyTests(unittest.TestCase):
    def test_default_api_key_is_valid_tv_client(self):
        index = apiKey.getDefaultIndex()
        item = apiKey.getItem(index)

        self.assertTrue(apiKey.isItemValid(index))
        self.assertEqual(item["platform"], "Tidal TV")
        self.assertEqual(item["clientId"], "4N3n6Q1x95LL5K7p")


if __name__ == "__main__":
    unittest.main()
