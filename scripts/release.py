"""Prepare CalVer releases and concise notes without importing the application."""

import argparse
import datetime as dt
import json
import os
import re
import subprocess
from pathlib import Path


VERSION_PATH = 'TIDALDL-PY/tidal_dl/printf.py'
VERSION_RE = re.compile(r"^VERSION\s*=\s*['\"]([^'\"]+)['\"]", re.MULTILINE)
TAG_RE = re.compile(r'v([0-9]{4})\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$')
TITLE_RE = re.compile(r'<!-- release-title: (.+?) -->')
CANDIDATE_BRANCH = 'release-candidate'
SOURCE_MARKER = 'Tidekeeper-Source: '
RELEASE_MARKER = 'Tidekeeper-Release: '
BOT_NAME = 'github-actions[bot]'
BOT_EMAIL = '41898282+github-actions[bot]@users.noreply.github.com'


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def git(*args):
    return command('git', *args)


def version_key(tag):
    match = TAG_RE.fullmatch(tag)
    if not match:
        raise ValueError(f'Invalid release tag: {tag}')
    parts = tuple(map(int, match.groups()))
    dt.date(*parts[:3])
    return parts


def next_version(tags, today):
    versions = [version_key(tag) for tag in tags if TAG_RE.fullmatch(tag)]
    date = (today.year, today.month, today.day)
    if versions and max(versions)[:3] > date:
        raise ValueError('A release is dated in the future; refusing to publish an older version')
    number = max((v[3] for v in versions if v[:3] == date), default=-1) + 1
    return '.'.join(map(str, (*date, number)))


def release_worthy(paths):
    exact = {
        'TIDALDL-PY/setup.py', 'TIDALDL-PY/requirements.txt',
        'TIDALDL-PY/pyproject.toml', 'TIDALDL-PY/MANIFEST.in',
    }
    return any(
        path in exact
        or (path.startswith('TIDALDL-PY/tidal_dl/') and not path.endswith('/supporters.json'))
        for path in paths
    )


def section(changelog, heading):
    match = re.search(rf'^## {re.escape(heading)}(?: - [^\n]+)?\n(.*?)(?=^## |\Z)',
                      changelog, re.MULTILINE | re.DOTALL)
    if not match:
        raise ValueError(f'Changelog is missing the {heading} section')
    return match


def short_title(text):
    text = re.sub(r'^(?:feat|fix|chore|build|ci|perf|refactor|docs|test)(?:\([^)]*\))?!?:\s*', '', text)
    text = re.sub(r'\s*\[skip ci\]\s*', '', text).strip().rstrip('.')
    text = re.sub(r'\s+', ' ', text)
    if not text:
        return 'Maintenance updates'
    text = text[0].upper() + text[1:]
    return text if len(text) <= 72 else text[:69].rsplit(' ', 1)[0] + '…'


def merge_notes(bodies):
    blocks = {}
    for body in bodies:
        current = []
        for line in [*body.splitlines(), '']:
            if not line.strip() or re.match(r'^[-*] ', line):
                if current:
                    block = '\n'.join(current)
                    blocks.setdefault(re.sub(r'\s+', ' ', block), block)
                    current = []
            if line.strip():
                current.append(line)
    return '\n\n'.join(blocks.values())


def prepare_notes(changelog, version, subjects, compare_url, pending_versions=()):
    unreleased = section(changelog, 'Unreleased')
    body = unreleased.group(1).strip()
    hint = TITLE_RE.search(body)
    body = TITLE_RE.sub('', body).strip()
    pending_bodies = []
    for pending in pending_versions:
        previous = section(changelog, pending).group(1).strip()
        previous = TITLE_RE.sub('', previous).strip()
        previous = re.sub(r'^\[Full changes\]\([^\n]+\)\s*$', '', previous, flags=re.MULTILINE).strip()
        if previous:
            pending_bodies.append(previous)
    if not body:
        summaries = []
        for subject in subjects:
            if subject.startswith(('Merge ', 'chore: release ', 'chore: refresh supporters')):
                continue
            summary = short_title(subject)
            if summary not in summaries:
                summaries.append(summary)
        body = '\n'.join(f'- {summary}.' for summary in summaries[:8]) or '- Maintenance updates.'
    first = re.sub(r'^[-*]\s*', '', body.splitlines()[0])
    title = short_title(hint.group(1) if hint else first)
    if pending_bodies:
        body = merge_notes([*pending_bodies, body])
    if compare_url:
        body += f'\n\n[Full changes]({compare_url})'
    date = '-'.join(f'{n:02d}' for n in version_key('v' + version)[:3])
    entry = f'## {version} - {date}\n\n<!-- release-title: {title} -->\n\n{body}\n\n'
    updated = changelog[:unreleased.start()] + '## Unreleased\n\n' + entry + changelog[unreleased.end():]
    return updated


def release_notes(root, tag):
    version_key(tag)
    version = VERSION_RE.search((root / VERSION_PATH).read_text(encoding='utf-8'))
    if not version or tag != 'v' + version.group(1):
        raise ValueError('Release tag does not match the package version')
    body = section((root / 'CHANGELOG.md').read_text(encoding='utf-8'), tag[1:]).group(1).strip()
    hint = TITLE_RE.search(body)
    body = TITLE_RE.sub('', body).strip()
    if not body:
        raise ValueError('Release notes must not be empty')
    title = short_title(hint.group(1) if hint else re.sub(r'^[-*]\s*', '', body.splitlines()[0]))
    return f'{tag} — {title}', body


def remote_tags():
    tags = {}
    for line in git('ls-remote', '--tags', 'origin', 'v*').splitlines():
        sha, ref = line.split()
        tag = ref.removeprefix('refs/tags/').removesuffix('^{}')
        if TAG_RE.fullmatch(tag):
            tags[tag] = sha
    return tags


def fetch_tag(tag):
    git('fetch', 'origin', f'refs/tags/{tag}:refs/tags/{tag}')


def remote_candidate():
    result = git('ls-remote', '--heads', 'origin', f'refs/heads/{CANDIDATE_BRANCH}')
    return result.split()[0] if result else None


def candidate_metadata(ref):
    body = git('show', '-s', '--format=%B', ref)
    source = next((line.removeprefix(SOURCE_MARKER) for line in body.splitlines()
                   if line.startswith(SOURCE_MARKER)), None)
    tag = next((line.removeprefix(RELEASE_MARKER) for line in body.splitlines()
                if line.startswith(RELEASE_MARKER)), None)
    if source and tag:
        version_key(tag)
    return source, tag


def configure_bot():
    git('config', 'user.name', BOT_NAME)
    git('config', 'user.email', BOT_EMAIL)


def published_tag(repository):
    result = subprocess.run(['gh', 'api', f'repos/{repository}/releases/latest'], text=True, capture_output=True)
    if result.returncode:
        if 'HTTP 404' in result.stderr:
            return None
        raise RuntimeError(result.stderr.strip())
    tag = json.loads(result.stdout)['tag_name']
    version_key(tag)
    return tag


def output_plan(ref, tag='', build=True, source=None):
    values = {'ref': ref, 'source': source or ref, 'tag': tag,
              'build': str(build).lower(), 'publish': str(bool(tag)).lower()}
    target = os.environ.get('GITHUB_OUTPUT')
    if target:
        with open(target, 'a', encoding='utf-8') as handle:
            for key, value in values.items():
                handle.write(f'{key}={value}\n')
    print(json.dumps(values))


def prepare(root, mode, source, ref, repository):
    if mode == 'preview':
        output_plan(source)
        return
    if ref != 'refs/heads/main':
        raise ValueError('Automatic releases must originate from main')
    if git('status', '--porcelain'):
        raise ValueError('Release preparation requires a clean checkout')
    tags = remote_tags()
    latest = max(tags, key=version_key) if tags else None
    if latest:
        fetch_tag(latest)
        # A rerun after the final tag exists must reuse the same immutable source.
        annotation = git('for-each-ref', '--format=%(contents)', f'refs/tags/{latest}')
        if tags[latest] == source or f'{SOURCE_MARKER}{source}' in annotation.splitlines():
            git('checkout', '--detach', latest)
            release_notes(root, latest)
            output_plan(git('rev-parse', 'HEAD'), latest, source=source)
            return
    git('fetch', 'origin', 'main')
    tip = git('rev-parse', 'FETCH_HEAD')
    if tip != source:
        print('Main advanced after this release was requested; preparing its current tip.')
        source = tip
    git('checkout', '--detach', tip)
    prepared_source, prepared_tag = candidate_metadata('HEAD')
    if prepared_source and prepared_tag:
        release_notes(root, prepared_tag)
        output_plan(tip, prepared_tag, source=prepared_source)
        return
    promoted = git('log', '--format=%H', f'--grep=^{RELEASE_MARKER}v', tip).splitlines()
    for commit in promoted:
        promoted_source, promoted_tag = candidate_metadata(commit)
        if promoted_source and promoted_tag and tags.get(promoted_tag) != commit:
            raise ValueError(
                f'{promoted_tag} was promoted but not tagged; rerun that failed release before publishing newer commits'
            )
    candidate = remote_candidate()
    if candidate:
        git('fetch', 'origin', f'refs/heads/{CANDIDATE_BRANCH}')
        candidate = git('rev-parse', 'FETCH_HEAD')
        candidate_source, candidate_tag = candidate_metadata(candidate)
        if candidate_source == source and candidate_tag:
            git('checkout', '--detach', candidate)
            release_notes(root, candidate_tag)
            output_plan(candidate, candidate_tag, source=source)
            return
        git('checkout', '--detach', tip)
    baseline = published_tag(repository)
    if baseline:
        fetch_tag(baseline)
    paths = git('diff', '--name-only', baseline, 'HEAD').splitlines() if baseline else git('ls-files').splitlines()
    if not release_worthy(paths):
        print('No application or build changes since the last release; running CI only.')
        output_plan(tip, build=False)
        return
    if not os.environ.get('PYPI_API_TOKEN'):
        raise ValueError('PYPI_API_TOKEN is required before preparing a release')
    version = next_version(tags, dt.datetime.now(dt.timezone.utc).date())
    tag = 'v' + version
    changelog = (root / 'CHANGELOG.md').read_text(encoding='utf-8')
    pending_versions = []
    for pending in sorted(tags, key=version_key):
        if baseline and version_key(pending) <= version_key(baseline):
            continue
        if re.search(rf'^## {re.escape(pending[1:])}(?: - [^\n]+)?$', changelog, re.MULTILINE):
            pending_versions.append(pending[1:])
    subjects = []
    if not TITLE_RE.sub('', section(changelog, 'Unreleased').group(1)).strip():
        summary_base = latest if pending_versions else baseline
        if summary_base:
            pages = json.loads(command('gh', 'api', '--paginate', '--slurp',
                                       f'repos/{repository}/compare/{summary_base}...{tip}?per_page=100'))
            subjects = [c['commit']['message'].splitlines()[0] for page in pages for c in page['commits']]
        else:
            subjects = [git('log', '-1', '--format=%s')]
    compare = f'https://github.com/{repository}/compare/{baseline}...{tag}' if baseline else ''
    updated = prepare_notes(changelog, version, subjects, compare, pending_versions)
    version_file = root / VERSION_PATH
    source_text = version_file.read_text(encoding='utf-8')
    if len(VERSION_RE.findall(source_text)) != 1:
        raise ValueError('Expected exactly one package VERSION')
    version_file.write_text(VERSION_RE.sub(f"VERSION = '{version}'", source_text), encoding='utf-8')
    (root / 'CHANGELOG.md').write_text(updated, encoding='utf-8')
    release_notes(root, tag)
    configure_bot()
    git('add', VERSION_PATH, 'CHANGELOG.md')
    git('commit', '-m', f'chore: prepare {tag} [skip ci]', '-m',
        f'{SOURCE_MARKER}{source}\n{RELEASE_MARKER}{tag}')
    candidate_commit = git('rev-parse', 'HEAD')
    push = ['push']
    if candidate:
        push.append(f'--force-with-lease=refs/heads/{CANDIDATE_BRANCH}:{candidate}')
    push.extend(('origin', f'HEAD:refs/heads/{CANDIDATE_BRANCH}'))
    try:
        git(*push)
    except subprocess.CalledProcessError:
        if remote_candidate() != candidate_commit:
            raise
    output_plan(candidate_commit, tag, source=source)


def promote(root, source, candidate, tag):
    """Advance main to a checked candidate without creating its public tag."""
    version_key(tag)
    git('fetch', 'origin', 'main')
    tip = git('rev-parse', 'FETCH_HEAD')
    if tip == candidate:
        return
    if tip != source:
        raise ValueError('Main changed after release checks; refusing to publish the candidate')
    git('checkout', '--detach', candidate)
    candidate_source, candidate_tag = candidate_metadata('HEAD')
    if (candidate_source, candidate_tag) != (source, tag):
        raise ValueError('Release candidate metadata does not match the checked source')
    release_notes(root, tag)
    try:
        git('push', 'origin', f'{candidate}:refs/heads/main')
    except subprocess.CalledProcessError:
        git('fetch', 'origin', 'main')
        if git('rev-parse', 'FETCH_HEAD') != candidate:
            raise


def tag_release(root, candidate, tag):
    """Create the version tag only after PyPI verified the candidate distributions."""
    version_key(tag)
    git('checkout', '--detach', candidate)
    source, candidate_tag = candidate_metadata('HEAD')
    if not source or candidate_tag != tag:
        raise ValueError('Release candidate metadata does not match the requested tag')
    release_notes(root, tag)
    existing = remote_tags().get(tag)
    if existing and existing != candidate:
        raise ValueError(f'{tag} already points to a different commit')
    if not existing:
        configure_bot()
        git('tag', '-a', tag, '-m', f'Tidekeeper automated release\n\n{SOURCE_MARKER}{source}')
        try:
            git('push', 'origin', f'refs/tags/{tag}')
        except subprocess.CalledProcessError:
            if remote_tags().get(tag) != candidate:
                raise
    if remote_candidate() == candidate:
        git('push', 'origin', '--delete', CANDIDATE_BRANCH)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    plan = commands.add_parser('prepare')
    plan.add_argument('--mode', choices=('auto', 'preview'), required=True)
    plan.add_argument('--source', required=True)
    plan.add_argument('--ref', required=True)
    plan.add_argument('--repository', required=True)
    notes = commands.add_parser('notes')
    notes.add_argument('--tag', required=True)
    notes.add_argument('--output', type=Path, required=True)
    promotion = commands.add_parser('promote')
    promotion.add_argument('--source', required=True)
    promotion.add_argument('--candidate', required=True)
    promotion.add_argument('--tag', required=True)
    tagging = commands.add_parser('tag')
    tagging.add_argument('--candidate', required=True)
    tagging.add_argument('--tag', required=True)
    args = parser.parse_args()
    root = Path.cwd()
    if args.command == 'prepare':
        prepare(root, args.mode, args.source, args.ref, args.repository)
    elif args.command == 'promote':
        promote(root, args.source, args.candidate, args.tag)
    elif args.command == 'tag':
        tag_release(root, args.candidate, args.tag)
    else:
        title, body = release_notes(root, args.tag)
        body += ('\n\nValidation: Python 3.10–3.14 CI and all five native platform builds passed.\n\n'
                 'Update with `python -m pip install --upgrade tidekeeper` or '
                 '`python -m pip install --upgrade "tidekeeper[gui]"`. '
                 'Standalone apps, checksums, and provenance attestations are attached. '
                 'FFmpeg remains a separate system dependency.\n')
        args.output.write_text(body, encoding='utf-8')
        print(title)


if __name__ == '__main__':
    main()
