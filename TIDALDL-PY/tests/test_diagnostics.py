"""The doctor command."""

import sys
import unittest
from unittest import mock

import tidal_dl
from tidal_dl import diagnostics
from tidal_dl.settings import SETTINGS

from fixtures import CatalogFixtures, ProfileFixture


class DoctorWriteCheckTests(ProfileFixture, unittest.TestCase):
    def test_doctor_preserves_existing_file_and_leaves_no_probe(self):
        sentinel = self.root / '.tidekeeper-write-test'
        sentinel.write_text('keep this file')
        SETTINGS.downloadPath = str(self.root)
        self.assertEqual(diagnostics._checkDownloadPath()[0], 'OK')
        self.assertEqual(sentinel.read_text(), 'keep this file')
        self.assertEqual(list(self.root.iterdir()), [sentinel])

    def test_doctor_warns_about_downloads_in_an_old_literal_tilde_folder(self):
        with mock.patch.object(diagnostics, 'legacyDownloadNotice', return_value='Move old downloads'):
            self.assertEqual(
                diagnostics._checkLegacyDownloads(),
                ('WARN', 'Earlier downloads', 'Move old downloads'),
            )
        with mock.patch.object(diagnostics, 'legacyDownloadNotice', return_value=None):
            self.assertIsNone(diagnostics._checkLegacyDownloads())


class DoctorCommandTests(CatalogFixtures, unittest.TestCase):
    def test_doctor_command_runs_without_login_or_download(self):
        old_argv = sys.argv
        sys.argv = ["tidekeeper", "--doctor"]
        try:
            with mock.patch.object(tidal_dl, "runDoctor", return_value=True) as doctor, \
                 mock.patch.object(tidal_dl, "loginByConfig") as login, \
                 mock.patch.object(tidal_dl, "start") as start:
                tidal_dl.mainCommand()
        finally:
            sys.argv = old_argv

        doctor.assert_called_once_with()
        login.assert_not_called()
        start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
