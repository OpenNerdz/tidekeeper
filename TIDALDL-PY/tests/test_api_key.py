import unittest

from tidal_dl import apiKey


class ApiKeyTests(unittest.TestCase):
    def test_default_api_key_is_valid_tv_client(self):
        index = apiKey.getDefaultIndex()
        item = apiKey.getItem(index)

        self.assertTrue(apiKey.isItemValid(index))
        self.assertEqual(item["platform"], "Tidal TV")
        self.assertEqual(item["clientId"], "4N3n6Q1x95LL5K7p")
        self.assertEqual(index, 4)

    def test_retired_clients_cannot_be_selected(self):
        self.assertEqual(apiKey.getLimitIndexs(), ['1', '4'])
        for index in (-1, 0, 2, 3, 5, 999):
            with self.subTest(index=index):
                self.assertFalse(apiKey.isItemValid(index))
                self.assertEqual(apiKey.getItem(index)['clientId'], '')

    def test_client_choices_preserve_saved_ids_and_hide_credentials_in_gui(self):
        from tidal_dl.gui_app.backend import DemoBackend, TidekeeperBackend
        items = apiKey.getItems()
        self.assertEqual([item['index'] for item in items], [1, 4])
        for item in items:
            self.assertEqual(item['clientId'], apiKey.getItem(item['index'])['clientId'])
        choices = TidekeeperBackend().api_clients()
        self.assertEqual(choices, DemoBackend().api_clients())
        self.assertEqual([item['index'] for item in choices], [1, 4])
        for item in choices:
            self.assertNotIn('clientId', item)
            self.assertNotIn('clientSecret', item)


if __name__ == "__main__":
    unittest.main()
