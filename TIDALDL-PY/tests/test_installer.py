"""Exercise installer branches with commands replaced by recording functions."""
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which('bash'), 'bash is not installed')
class InstallerTests(unittest.TestCase):
    def run_installer_function(self, script):
        installer = Path(__file__).resolve().parents[2] / 'install.sh'
        if not installer.exists():
            self.skipTest('Installer is only included in the repository checkout')
        return subprocess.run(
            ['bash', '-c', 'source "$1"\n' + script, 'installer-test', str(installer)],
            check=True, capture_output=True, text=True,
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

