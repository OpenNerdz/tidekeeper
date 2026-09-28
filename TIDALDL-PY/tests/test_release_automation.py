"""Release preparation is exercised against disposable local Git repositories."""

import contextlib
import datetime as dt
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'


def load_helper(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if (SCRIPTS / 'release.py').exists():
    release = load_helper('release', 'release.py')
    with mock.patch.dict(sys.modules, {'release': release}):
        publish = load_helper('publish_release', 'publish-release.py')
else:
    release = publish = None


@unittest.skipIf(release is None, 'Release helpers are only included in the checkout')
class ReleaseMetadataTests(unittest.TestCase):
    def test_daily_counter_includes_reserved_tags_and_resets_on_a_new_day(self):
        tags = ['v2026.9.27.7', 'v2026.9.28.0', 'v2026.9.28.1', 'unrelated']
        self.assertEqual(release.next_version(tags, dt.date(2026, 9, 28)), '2026.9.28.2')
        self.assertEqual(release.next_version(tags, dt.date(2026, 9, 29)), '2026.9.29.0')

    def test_future_release_and_invalid_calendar_dates_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'future'):
            release.next_version(['v2026.9.29.0'], dt.date(2026, 9, 28))
        with self.assertRaises(ValueError):
            release.version_key('v2026.2.30.0')

    def test_notes_keep_curated_bullets_and_title_and_reopen_unreleased(self):
        original = ('# Changelog\n\n## Unreleased\n\n'
                    '<!-- release-title: Reliable downloads -->\n\n'
                    '- Fix retries.\n- Keep saved settings.\n\n## 2026.9.27.0 - 2026-09-27\n\n- Previous.\n')
        result = release.prepare_notes(original, '2026.9.28.0', ['Ignored commit'], 'https://example.com/compare')
        self.assertIn('## Unreleased\n\n## 2026.9.28.0 - 2026-09-28', result)
        self.assertIn('<!-- release-title: Reliable downloads -->', result)
        self.assertIn('- Fix retries.\n- Keep saved settings.', result)
        self.assertIn('[Full changes](https://example.com/compare)', result)
        self.assertIn('## 2026.9.27.0 - 2026-09-27\n\n- Previous.', result)
        self.assertNotIn('Ignored commit', result)

    def test_fallback_notes_remove_noise_and_duplicate_subjects(self):
        result = release.prepare_notes('## Unreleased\n', '2026.9.28.0', [
            'Merge pull request #5', 'fix: handle retries', 'fix: handle retries',
            'chore: refresh supporters [skip ci]', 'perf(gui): speed up search',
        ], '')
        self.assertIn('- Handle retries.', result)
        self.assertIn('- Speed up search.', result)
        self.assertEqual(result.count('- Handle retries.'), 1)
        self.assertNotIn('Merge pull', result)
        self.assertNotIn('refresh supporters', result)

    def test_docs_tests_and_generated_supporters_do_not_trigger_a_release(self):
        self.assertFalse(release.release_worthy([
            'README.md', 'CHANGELOG.md', 'TIDALDL-PY/tests/test_sample.py',
            'TIDALDL-PY/tidal_dl/gui_app/supporters.json', '.github/workflows/supporters.yml',
        ]))
        for path in ('TIDALDL-PY/tidal_dl/download.py', 'TIDALDL-PY/requirements.txt',
                     '.github/workflows/build.yml', 'scripts/release.py', 'build.sh'):
            self.assertTrue(release.release_worthy([path]))

    def test_failed_release_notes_are_carried_into_the_next_release(self):
        original = ('## Unreleased\n\n<!-- release-title: Complete retry fixes -->\n\n- Fix publishing.\n\n'
                    '## 2026.9.28.0 - 2026-09-28\n\n<!-- release-title: Retry fixes -->\n\n'
                    '- Fix download retries.\n\n[Full changes](https://example.com/old)\n')
        result = release.prepare_notes(original, '2026.9.28.1', [], 'https://example.com/new', ['2026.9.28.0'])
        new = release.section(result, '2026.9.28.1').group(1)
        self.assertIn('- Fix download retries.', new)
        self.assertIn('- Fix publishing.', new)
        self.assertIn('Complete retry fixes', new)
        self.assertNotIn('https://example.com/old', new)

    def test_repeated_failed_attempts_do_not_duplicate_notes(self):
        result = release.merge_notes(['- Fix retries.\n- Keep settings.',
                                      '- Fix retries.\n\n- Keep\n  settings.\n\n- Fix publishing.'])
        self.assertEqual(result.count('- Fix retries.'), 1)
        self.assertEqual(result.count('- Keep settings.'), 1)
        self.assertIn('- Fix publishing.', result)


@unittest.skipUnless(release and shutil.which('git'), 'Release helpers and Git are required')
class ReleaseGitTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.remote = self.root / 'remote.git'
        self.repo = self.root / 'checkout'
        self.run_git('init', '--bare', str(self.remote), cwd=self.root)
        self.run_git('init', '-b', 'main', str(self.repo), cwd=self.root)
        self.run_git('config', 'user.name', 'Release test')
        self.run_git('config', 'user.email', 'test@example.invalid')
        self.run_git('remote', 'add', 'origin', str(self.remote))
        version_file = self.repo / release.VERSION_PATH
        version_file.parent.mkdir(parents=True)
        version_file.write_text("VERSION = '2020.1.1.0'\n")
        (self.repo / 'CHANGELOG.md').write_text(
            '# Changelog\n\n## Unreleased\n\n<!-- release-title: Reliable builds -->\n\n'
            '- Improve builds.\n\n## 2020.1.1.0 - 2020-01-01\n\n- Initial release.\n')
        self.run_git('add', '.')
        self.run_git('commit', '-m', 'Initial')
        self.run_git('tag', '-a', 'v2020.1.1.0', '-m', 'Initial release')
        self.run_git('push', 'origin', 'main', '--tags')
        self.original_cwd = Path.cwd()
        os.chdir(self.repo)
        self.addCleanup(os.chdir, self.original_cwd)
        patch = mock.patch.dict(os.environ, {'PYPI_API_TOKEN': 'local-test-placeholder', 'GITHUB_OUTPUT': ''})
        patch.start()
        self.addCleanup(patch.stop)
        baseline = mock.patch.object(release, 'published_tag', return_value='v2020.1.1.0')
        baseline.start()
        self.addCleanup(baseline.stop)

    def run_git(self, *args, cwd=None):
        return subprocess.check_output(['git', *args], cwd=cwd or self.repo, text=True,
                                       stderr=subprocess.PIPE).strip()

    def change(self, path, text, message='Improve builds'):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        self.run_git('add', path)
        self.run_git('commit', '-m', message)
        self.run_git('push', 'origin', 'HEAD:main')
        return self.run_git('rev-parse', 'HEAD')

    def prepare(self, source):
        with mock.patch.object(release, 'output_plan') as plan, contextlib.redirect_stdout(io.StringIO()):
            release.prepare(self.repo, 'auto', source, 'refs/heads/main', 'example/repository')
        return plan.call_args

    def test_release_updates_main_and_tag_together_and_rerun_reuses_them(self):
        source = self.change('TIDALDL-PY/tidal_dl/app.py', 'VALUE = 1\n')
        result = self.prepare(source)
        sha, tag = result.args
        self.assertEqual(self.run_git('ls-remote', 'origin', 'refs/heads/main').split()[0], sha)
        self.assertEqual(self.run_git('rev-parse', tag + '^{}'), sha)
        self.assertIn(tag[1:], self.run_git('show', f'{tag}:{release.VERSION_PATH}'))
        title, body = release.release_notes(self.repo, tag)
        self.assertEqual(title, f'{tag} — Reliable builds')
        self.assertIn('- Improve builds.', body)
        self.assertNotIn('release-title', body)
        original_tags = self.run_git('ls-remote', '--tags', 'origin')
        self.assertEqual(self.prepare(source).args, result.args)
        self.assertEqual(self.run_git('ls-remote', '--tags', 'origin'), original_tags)

    def test_documentation_only_push_keeps_version_and_tag_unchanged(self):
        source = self.change('README.md', 'Updated docs\n')
        result = self.prepare(source)
        self.assertEqual(result.args, (source,))
        self.assertEqual(result.kwargs, {'build': False})
        self.assertEqual(self.run_git('tag', '--list'), 'v2020.1.1.0')

    def test_next_push_after_failed_release_keeps_daily_counter_and_carries_notes(self):
        source = self.change('TIDALDL-PY/tidal_dl/app.py', 'VALUE = 1\n')
        first_tag = self.prepare(source).args[1]
        next_source = self.change('TIDALDL-PY/tidal_dl/app.py', 'VALUE = 2\n', 'fix: improve retries')
        original_command = release.command

        def compare_response(*args):
            if args[0] == 'gh':
                return json.dumps([{'commits': [{'commit': {'message': 'fix: improve retries'}}]}])
            return original_command(*args)

        with mock.patch.object(release, 'command', side_effect=compare_response):
            second_tag = self.prepare(next_source).args[1]
        self.assertEqual(release.version_key(second_tag)[:3], release.version_key(first_tag)[:3])
        self.assertEqual(release.version_key(second_tag)[3], release.version_key(first_tag)[3] + 1)
        _, body = release.release_notes(self.repo, second_tag)
        self.assertIn('- Improve builds.', body)
        self.assertIn('- Improve retries.', body)

    def test_newer_application_push_supersedes_old_run(self):
        source = self.change('TIDALDL-PY/tidal_dl/app.py', 'VALUE = 1\n')
        self.change('TIDALDL-PY/tidal_dl/app.py', 'VALUE = 2\n')
        result = self.prepare(source)
        self.assertFalse(result.kwargs['build'])
        self.assertEqual(self.run_git('tag', '--list'), 'v2020.1.1.0')

    def test_supporter_bot_commit_does_not_lose_pending_application_release(self):
        source = self.change('TIDALDL-PY/tidal_dl/app.py', 'VALUE = 1\n')
        self.change('TIDALDL-PY/tidal_dl/gui_app/supporters.json', '["new-user"]\n')
        result = self.prepare(source)
        self.assertEqual(len(result.args), 2)
        self.assertEqual(json.loads((self.repo / 'TIDALDL-PY/tidal_dl/gui_app/supporters.json').read_text()), ['new-user'])

    def test_competing_push_cannot_overwrite_main_or_leave_a_remote_release_tag(self):
        source = self.change('TIDALDL-PY/tidal_dl/app.py', 'VALUE = 1\n')
        original_git = release.git

        def competing_git(*args):
            if args[:2] == ('push', '--atomic'):
                tree = self.run_git('rev-parse', source + '^{tree}')
                competing = self.run_git('commit-tree', tree, '-p', source, '-m', 'Concurrent commit')
                self.run_git('push', 'origin', competing + ':refs/heads/main')
            return original_git(*args)

        with mock.patch.object(release, 'git', side_effect=competing_git):
            result = self.prepare(source)
        self.assertFalse(result.kwargs['build'])
        tags = self.run_git('ls-remote', '--tags', 'origin')
        self.assertEqual(len(tags.splitlines()), 2)  # Initial annotated tag only.

    def test_lost_push_response_recovers_without_allocating_a_second_tag(self):
        source = self.change('TIDALDL-PY/tidal_dl/app.py', 'VALUE = 1\n')
        original_git = release.git
        pushed = False

        def lost_response(*args):
            nonlocal pushed
            output = original_git(*args)
            if args[:2] == ('push', '--atomic') and not pushed:
                pushed = True
                raise subprocess.CalledProcessError(1, args)
            return output

        with mock.patch.object(release, 'git', side_effect=lost_response):
            result = self.prepare(source)
        self.assertEqual(len(result.args), 2)
        self.assertEqual(len(self.run_git('ls-remote', '--tags', 'origin').splitlines()), 4)

    def test_dirty_checkout_is_never_reset_or_released(self):
        source = self.run_git('rev-parse', 'HEAD')
        (self.repo / 'README.md').write_text('Unsaved work\n')
        with self.assertRaisesRegex(ValueError, 'clean checkout'):
            self.prepare(source)
        self.assertEqual((self.repo / 'README.md').read_text(), 'Unsaved work\n')


@unittest.skipIf(publish is None, 'Release helpers are only included in the checkout')
class ReleasePublishTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.tag = 'v2026.9.28.1'
        for name in ('tidekeeper-2026.9.28.1.tar.gz', 'tidekeeper-2026.9.28.1-py3-none-any.whl'):
            (self.directory / name).write_bytes(name.encode())

    def assets(self):
        return [{'name': name, 'size': 123, 'state': 'uploaded'}
                for name in publish.expected_assets() | {'SHA256SUMS'}]

    def test_partial_pypi_upload_resumes_only_missing_file(self):
        wheel = next(self.directory.glob('*.whl'))
        pending = publish.missing_distributions(self.directory, self.tag, {wheel.name: publish.digest(wheel)})
        self.assertEqual([p.suffix for p in pending], ['.gz'])
        complete = {p.name: publish.digest(p) for p in self.directory.iterdir()}
        self.assertEqual(publish.missing_distributions(self.directory, self.tag, complete), [])

    def test_existing_pypi_file_with_different_bytes_stops_release(self):
        wheel = next(self.directory.glob('*.whl'))
        with self.assertRaisesRegex(ValueError, 'different bytes'):
            publish.missing_distributions(self.directory, self.tag, {wheel.name: '0' * 64})

    def test_missing_empty_or_unexpected_distribution_stops_release(self):
        wheel = next(self.directory.glob('*.whl'))
        wheel.write_bytes(b'')
        with self.assertRaisesRegex(ValueError, 'nonempty'):
            publish.missing_distributions(self.directory, self.tag, {})
        wheel.unlink()
        with self.assertRaisesRegex(ValueError, 'missing='):
            publish.missing_distributions(self.directory, self.tag, {})

    def test_incomplete_github_draft_is_never_published(self):
        with mock.patch.object(publish, 'gh_json', return_value={'draft': True, 'assets': []}), \
                mock.patch.object(publish.subprocess, 'run') as run, \
                self.assertRaisesRegex(ValueError, 'complete platform'):
            publish.finalize('example/repo', self.tag)
        run.assert_not_called()

    def test_draft_lookup_paginates_and_fetches_by_id_after_tag_not_found(self):
        draft = {'id': 123, 'tag_name': self.tag, 'draft': True, 'assets': self.assets()}
        with mock.patch.object(publish, 'gh_json', side_effect=[
            None, [{'tag_name': 'v2026.9.27.0'}] * 100, [draft], draft,
        ]) as api:
            self.assertEqual(publish.github_release('example/repo', self.tag), draft)
        self.assertEqual(api.call_args_list, [
            mock.call(f'repos/example/repo/releases/tags/{self.tag}'),
            mock.call('repos/example/repo/releases?per_page=100&page=1'),
            mock.call('repos/example/repo/releases?per_page=100&page=2'),
            mock.call('repos/example/repo/releases/123'),
        ])

    def test_missing_release_is_distinct_from_inaccessible_repository(self):
        with mock.patch.object(publish, 'gh_json', side_effect=[None, []]):
            self.assertIsNone(publish.github_release('example/repo', self.tag))
        with mock.patch.object(publish, 'gh_json', side_effect=[None, None]), \
                self.assertRaisesRegex(ValueError, 'inaccessible'):
            publish.github_release('example/repo', self.tag)

    def test_existing_draft_is_updated_without_creating_a_duplicate(self):
        for path in self.directory.iterdir():
            path.unlink()
        for asset in self.assets():
            (self.directory / asset['name']).write_bytes(b'asset')
        draft = {'id': 123, 'tag_name': self.tag, 'draft': True, 'assets': self.assets()}
        with mock.patch.object(publish, 'gh_json', side_effect=[None, [draft], draft] * 2), \
                mock.patch.object(publish, 'release_notes', return_value=('Release title', 'Notes')), \
                mock.patch.object(publish.subprocess, 'run') as run:
            publish.github_draft('example/repo', self.tag, self.directory, Path('notes.md'))
        self.assertEqual([call.args[0][2] for call in run.call_args_list], ['edit', 'upload'])

    def test_draft_found_by_id_is_published_after_asset_validation(self):
        draft = {'id': 123, 'tag_name': self.tag, 'draft': True, 'assets': self.assets()}
        with mock.patch.object(publish, 'gh_json', side_effect=[
            None, [draft], draft, {'tag_name': 'v2026.9.28.0'},
        ]), mock.patch.object(publish.subprocess, 'run') as run:
            publish.finalize('example/repo', self.tag)
        self.assertIn('--draft=false', run.call_args.args[0])
        self.assertIn('--latest', run.call_args.args[0])

    def test_old_release_retry_does_not_replace_newer_latest_release(self):
        with mock.patch.object(publish, 'gh_json', side_effect=[
            {'draft': True, 'assets': self.assets()}, {'tag_name': 'v2026.9.29.0'},
        ]), mock.patch.object(publish.subprocess, 'run') as run:
            publish.finalize('example/repo', self.tag)
        self.assertIn('--latest=false', run.call_args.args[0])

    def test_already_public_release_is_not_modified(self):
        with mock.patch.object(publish, 'gh_json', return_value={'draft': False, 'assets': self.assets()}), \
                mock.patch.object(publish.subprocess, 'run') as run:
            publish.finalize('example/repo', self.tag)
        run.assert_not_called()
