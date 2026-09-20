import socket
import unittest
from unittest import mock

from tidal_dl import network_policy
from tidal_dl.network_policy import UnsafeMediaUrl, validate_media_url


class NetworkPolicyTests(unittest.TestCase):
    def setUp(self):
        network_policy._dns_cache.clear()

    def test_rejects_private_literal_local_name_and_credentials(self):
        for url in (
            'http://127.0.0.1/media',
            'http://[::1]/media',
            'http://localhost/media',
            'https://user:password@example.com/media',
            'file:///etc/passwd',
        ):
            with self.subTest(url=url), self.assertRaises(UnsafeMediaUrl):
                validate_media_url(url)

    def test_rejects_hostname_resolving_to_private_address(self):
        records = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('10.0.0.2', 0))]
        with mock.patch.object(socket, 'getaddrinfo', return_value=records), self.assertRaises(UnsafeMediaUrl):
            validate_media_url('https://cdn.example/media')

    def test_accepts_public_https_host(self):
        records = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('1.1.1.1', 0))]
        with mock.patch.object(socket, 'getaddrinfo', return_value=records):
            self.assertEqual(validate_media_url('https://cdn.example/media'), 'https://cdn.example/media')


if __name__ == '__main__':
    unittest.main()
