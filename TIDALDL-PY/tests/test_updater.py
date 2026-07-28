import sys
import unittest
from unittest import mock

from tidal_dl import updater


class UpdaterTests(unittest.TestCase):
    def test_update_target_selects_terminal_or_gui_extra(self):
        self.assertEqual(
            updater.update_target(False),
            "tidekeeper @ git+https://github.com/OpenNerdz/tidekeeper.git#subdirectory=TIDALDL-PY",
        )
        self.assertEqual(
            updater.update_target(True),
            "tidekeeper[gui] @ git+https://github.com/OpenNerdz/tidekeeper.git#subdirectory=TIDALDL-PY",
        )

    def test_update_command_uses_current_python(self):
        command = updater.update_command(True)
        self.assertEqual(command[:4], [sys.executable, "-m", "pip", "install"])
        self.assertIn("--upgrade", command)
        self.assertEqual(command[-1], updater.update_target(True))

    def test_standalone_build_does_not_run_pip(self):
        with mock.patch.object(sys, "frozen", True, create=True):
            with mock.patch.object(updater.subprocess, "run") as run:
                result = updater.run_update(True)

        self.assertFalse(result.ok)
        self.assertTrue(result.standalone)
        self.assertIn(updater.RELEASES_URL, result.message)
        run.assert_not_called()

    def test_run_update_reports_process_launch_failure(self):
        with mock.patch.object(updater.subprocess, "run", side_effect=OSError("pip unavailable")):
            result = updater.run_update(False)

        self.assertFalse(result.ok)
        self.assertIn("pip unavailable", result.output)
        self.assertEqual(result.command, updater.update_command(False))

    def test_run_update_returns_pip_output(self):
        completed = mock.Mock(returncode=0, stdout="updated\n")

        with mock.patch.object(updater.subprocess, "run", return_value=completed) as run:
            result = updater.run_update(False)

        self.assertTrue(result.ok)
        self.assertEqual(result.output, "updated\n")
        self.assertEqual(result.command, updater.update_command(False))
        run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
