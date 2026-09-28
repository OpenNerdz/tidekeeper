"""Exercise the scheduled snapshot updater without GitHub access."""

import json
import runpy
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/update-supporters.py'


@unittest.skipUnless(SCRIPT.exists(), 'Snapshot helper is only included in the repository')
class SupporterSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.update = runpy.run_path(str(SCRIPT))['update_supporters']
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.target = Path(temporary.name) / 'supporters.json'
        self.target.write_text('["former-star"]\n')

    def test_pages_are_combined_sorted_and_deduplicated_and_unstars_removed(self):
        self.assertTrue(self.update([[{'login': 'Zoe'}], [{'login': 'Alice'}, {'login': 'alice'}]], self.target))
        self.assertEqual(json.loads(self.target.read_text()), ['Alice', 'Zoe'])

    def test_reordered_responses_do_not_rewrite_snapshot(self):
        self.update([[{'login': 'Zoe'}, {'login': 'Alice'}]], self.target)
        original = self.target.stat().st_mtime_ns
        self.assertFalse(self.update([[{'login': 'Alice'}, {'login': 'Zoe'}]], self.target))
        self.assertEqual(self.target.stat().st_mtime_ns, original)

    def test_invalid_or_missing_pages_preserve_existing_snapshot(self):
        for payload in ([], {}, [None], [[{}]], [[{'login': '../bad'}]], [[{'login': 'ok'}], {'message': 'error'}]):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.update(payload, self.target)
            self.assertEqual(self.target.read_text(), '["former-star"]\n')

    def test_valid_empty_page_clears_all_former_stars(self):
        self.assertTrue(self.update([[]], self.target))
        self.assertEqual(json.loads(self.target.read_text()), [])
