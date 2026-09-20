import unittest

from tidal_dl import apiKey


class ApiKeyTests(unittest.TestCase):
    def test_default_api_key_supports_hires_lossless(self):
        from tidal_dl.settings import Settings

        index = apiKey.getDefaultIndex()
        item = apiKey.getItem(index)

        self.assertTrue(apiKey.isItemValid(index))
        self.assertEqual(item["platform"], "Tidal HiRes")
        self.assertIn("24-bit/192 kHz", item["formats"])
        self.assertEqual(item["clientId"], "fX2JxdmntZWK0ixT")
        self.assertEqual(index, 5)
        self.assertEqual(Settings().apiKeyIndex, index)

    def test_retired_clients_cannot_be_selected(self):
        self.assertEqual(apiKey.getLimitIndexs(), ['1', '4', '5'])
        for index in (-1, 0, 2, 3, 6, 999):
            with self.subTest(index=index):
                self.assertFalse(apiKey.isItemValid(index))
                self.assertEqual(apiKey.getItem(index)['clientId'], '')

    def test_client_choices_preserve_saved_ids_and_hide_credentials_in_gui(self):
        from tidal_dl.gui_app.backend import DemoBackend, TidekeeperBackend
        items = apiKey.getItems()
        self.assertEqual([item['index'] for item in items], [1, 4, 5])
        for item in items:
            self.assertEqual(item['clientId'], apiKey.getItem(item['index'])['clientId'])
        choices = TidekeeperBackend().api_clients()
        self.assertEqual(choices, DemoBackend().api_clients())
        self.assertEqual([item['index'] for item in choices], [1, 4, 5])
        for item in choices:
            self.assertNotIn('clientId', item)
            self.assertNotIn('clientSecret', item)


if __name__ == "__main__":
    unittest.main()
