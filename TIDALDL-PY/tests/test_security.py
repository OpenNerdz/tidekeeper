"""Credential handling and redaction."""

import io
import threading
import unittest
from contextlib import redirect_stdout
from unittest import mock

import requests

from tidal_dl import download, runtime
from tidal_dl.printf import Printf
from tidal_dl.runtime import redact

from fixtures import ApiFixture, TransferFixture


class TokenRedactionTests(TransferFixture, unittest.TestCase):
    def test_redaction_covers_gui_and_service_token_names(self):
        message = 'accessToken="dummy-access" refresh_token=dummy-refresh Bearer dummy-bearer https://cdn.invalid/file?token=dummy-query'
        result = redact(message)
        for secret in ['dummy-access', 'dummy-refresh', 'dummy-bearer', 'dummy-query']:
            self.assertNotIn(secret, result)


class CredentialProtectionTests(ApiFixture, unittest.TestCase):
    def test_secret_prompt_uses_hidden_input(self):
        with mock.patch('tidal_dl.printf.getpass.getpass', return_value='sample-token') as secret:
            self.assertEqual(Printf.enterSecret('Token:'), 'sample-token')
        secret.assert_called_once()

    def test_console_file_and_job_output_all_redact_credentials(self):
        message = 'accessToken=sample-access refresh_token=sample-refresh Bearer sample-bearer'
        outputs = [io.StringIO(), io.StringIO()]
        with redirect_stdout(outputs[0]):
            runtime.print(message)
        runtime.print(message, file=outputs[1])
        job_output = []
        with runtime.job_context(job_output.append):
            runtime.print(message)
        for value in [*(output.getvalue() for output in outputs), ''.join(job_output)]:
            self.assertNotIn('sample-', value)
            self.assertIn('[redacted]', value)
        self.assertEqual(runtime.redact('AccessToken good for 1 hour.'), 'AccessToken good for 1 hour.')

    def test_url_credentials_are_redacted(self):
        value = runtime.redact('https://user:sample-password@example.com/file?token=sample-query')
        self.assertNotIn('sample-', value)

    def test_public_media_does_not_use_automatic_netrc_credentials(self):
        with mock.patch.object(download, 'download_session_state', threading.local()):
            session = download._httpSession()
            try:
                with mock.patch('requests.sessions.get_netrc_auth', return_value=('user', 'sample-password')) as netrc:
                    request = session.prepare_request(requests.Request('GET', 'https://cdn.example/media'))
                netrc.assert_not_called()
                self.assertNotIn('Authorization', request.headers)
            finally:
                session.close()


if __name__ == "__main__":
    unittest.main()
