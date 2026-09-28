"""Release metadata errors must be caught before starting platform builds."""

import runpy
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/check-release.py"


@unittest.skipUnless(SCRIPT.exists(), "Release helper is only included in the repository")
class ReleasePreflightTests(unittest.TestCase):
    def setUp(self):
        self.check_release = runpy.run_path(str(SCRIPT))["check_release"]
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.version_file = self.root / "TIDALDL-PY/tidal_dl/printf.py"
        self.version_file.parent.mkdir(parents=True)
        # Validation must not import application code or require dependencies.
        self.version_file.write_text("VERSION = '2026.9.28.0'\nraise RuntimeError('do not import')\n")
        self.changelog = self.root / "CHANGELOG.md"
        self.changelog.write_text("# Changelog\n\n## Unreleased\n\n## 2026.9.28.0 - 2026-09-28\n")

    def test_matching_tag_passes_without_importing_application(self):
        self.assertIn("agree", self.check_release(self.root, "refs/tags/v2026.9.28.0"))

    def test_branch_build_needs_no_release_metadata(self):
        self.version_file.unlink()
        self.changelog.unlink()
        self.assertIn("no release", self.check_release(self.root, "refs/heads/main"))

    def test_mismatched_version_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.check_release(self.root, "refs/tags/v2026.9.28.1")

    def test_invalid_tags_are_rejected(self):
        for tag in ("vnext", "v2026.09.28.0", "2026.9.28.0", "v2026.9.28.0rc1"):
            with self.subTest(tag=tag), self.assertRaisesRegex(ValueError, "must use"):
                self.check_release(self.root, f"refs/tags/{tag}")

    def test_missing_version_is_rejected(self):
        self.version_file.write_text("# No version\n")
        with self.assertRaisesRegex(ValueError, "Unable to find"):
            self.check_release(self.root, "refs/tags/v2026.9.28.0")

    def test_unreleased_or_different_release_does_not_satisfy_changelog(self):
        for heading in ("## Unreleased", "## 2026.9.28.01", "### 2026.9.28.0", "## 2026x9x28x0"):
            self.changelog.write_text(f"{heading}\nMentions 2026.9.28.0 in prose.\n")
            with self.subTest(heading=heading), self.assertRaisesRegex(ValueError, "no release section"):
                self.check_release(self.root, "refs/tags/v2026.9.28.0")

    def test_release_heading_without_date_is_accepted(self):
        self.changelog.write_text("## 2026.9.28.0\n\n- Changes\n")
        self.assertIn("agree", self.check_release(self.root, "refs/tags/v2026.9.28.0"))
