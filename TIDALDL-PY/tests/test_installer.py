"""Exercise installer branches with commands replaced by recording functions."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


@unittest.skipUnless(shutil.which('bash'), 'bash is not installed')
class InstallerTests(unittest.TestCase):
    def run_installer_function(self, script, cwd=None):
        installer = Path(__file__).resolve().parents[2] / 'install.sh'
        if not installer.exists():
            self.skipTest('Installer is only included in the repository checkout')
        return subprocess.run(
            ['bash', '-c', 'source "$1"\n' + script, 'installer-test', str(installer)],
            check=True, capture_output=True, text=True, cwd=cwd,
        ).stdout

    def test_termux_uses_package_manager_for_pip(self):
        output = self.run_installer_function('''
python_command() { echo fake_python; }
fake_python() { echo "python $*"; }
pkg() { echo "pkg $*"; }
install_termux_dependencies
install_termux_package
''')
        self.assertIn('pkg install -y python python-pip ', output)
        self.assertIn('python -m pip install --upgrade wheel', output)
        self.assertNotIn('install --upgrade pip', output)

    def test_arch_install_does_not_perform_partial_upgrade(self):
        output = self.run_installer_function('''
id() { echo 0; }
has_command() { [[ "$1" == pacman ]]; }
run_as_root() { echo "$*"; }
install_linux_dependencies
''')
        self.assertIn('pacman -Syu --needed', output)

    def test_failed_apt_update_stops_dependency_install_in_error_handler(self):
        output = self.run_installer_function('''
id() { echo 0; }
has_command() { [[ "$1" == apt-get ]]; }
run_as_root() { echo "$*"; [[ "$2" != update ]]; }
if install_linux_dependencies; then
    exit 99
else
    echo "dependency failure: $?"
fi
''')
        self.assertIn('apt-get update', output)
        self.assertNotIn('apt-get install', output)
        self.assertIn('dependency failure: 1', output)

    def test_relative_install_root_creates_working_command_links(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.run_installer_function('''
INSTALL_ROOT="relative/install root"
BIN_DIR="relative/bin dir"
python_command() { echo fake_python; }
fake_python() {
    [[ "$1 $2" == "-m venv" ]]
    mkdir -p "$3/bin"
    printf '#!/bin/sh\\nexit 0\\n' > "$3/bin/python"
    chmod +x "$3/bin/python"
    touch "$3/bin/tidekeeper" "$3/bin/tidal-dl"
}
install_linux_package
''', cwd=temporary)
            root = Path(temporary)
            for name in ('tidekeeper', 'tidal-dl'):
                command = root / 'relative/bin dir' / name
                self.assertTrue(command.is_file(), f'{name} link is broken')
                self.assertEqual(command.resolve(), root / 'relative/install root/venv/bin' / name)
