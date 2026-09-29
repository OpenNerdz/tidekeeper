"""Validate release files, resume PyPI uploads, and publish complete GitHub releases."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from release import release_notes, version_key

PYPI_INDEX_URL = 'https://pypi.org/simple/tidekeeper/'
# Up to about six minutes for a new upload to appear in the index.
PYPI_POLL_SECONDS = 15
PYPI_VISIBILITY_ATTEMPTS = 24
PYPI_REQUEST_ATTEMPTS = 3


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def expected_assets():
    return {
        f'{app}-{platform}{extension}'
        for app in ('tidekeeper', 'tidekeeper-gui')
        for platform, extension in (
            ('Linux-x86_64', '.tar.gz'), ('Linux-arm64', '.tar.gz'),
            ('macOS-x86_64', '.tar.gz'), ('macOS-arm64', '.tar.gz'), ('Windows-x86_64', '.exe'),
        )
    }


def validate_files(directory, expected):
    actual = {path.name for path in directory.iterdir()}
    if actual != expected:
        raise ValueError(f'Unexpected release files: missing={sorted(expected - actual)}, extra={sorted(actual - expected)}')
    if any(not (directory / name).is_file() or (directory / name).stat().st_size == 0 for name in expected):
        raise ValueError('Release files must be nonempty regular files')


def pypi_files(tag):
    """Files pip's package index lists for this version, as {filename: sha256}.

    PyPI refreshes this index on upload. The per-version JSON API is avoided: its
    CDN caches the "not found" answer from the check made before uploading.
    """
    version_key(tag)
    version = tag[1:]
    request = urllib.request.Request(PYPI_INDEX_URL, headers={
        'Accept': 'application/vnd.pypi.simple.v1+json', 'User-Agent': 'Tidekeeper-release',
    })
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return {}
        raise
    sdist = f'tidekeeper-{version}.tar.gz'
    return {item['filename']: item['hashes']['sha256'] for item in payload.get('files', [])
            if item['filename'] == sdist or item['filename'].startswith(f'tidekeeper-{version}-')}


def _transient(error):
    if isinstance(error, urllib.error.HTTPError):
        return error.code == 429 or error.code >= 500
    return True


def read_pypi(tag, attempts=PYPI_REQUEST_ATTEMPTS, interval=5):
    """pypi_files, retried through brief network, server, or truncated-response errors."""
    for attempt in range(attempts):
        try:
            return pypi_files(tag)
        except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError) as error:
            if not _transient(error) or attempt == attempts - 1:
                raise
            print(f'PyPI request failed ({error}); retrying')
            time.sleep(interval)


def wait_for_pypi(directory, tag, attempts=PYPI_VISIBILITY_ATTEMPTS, interval=PYPI_POLL_SECONDS):
    """Wait until PyPI's index lists both validated files with matching hashes."""
    for attempt in range(attempts):
        if not missing_distributions(directory, tag, read_pypi(tag)):
            print('Both PyPI distribution hashes match the validated build')
            return
        if attempt < attempts - 1:
            print(f'Waiting for PyPI to list {tag} ({attempt + 1}/{attempts})')
            time.sleep(interval)
    raise RuntimeError('PyPI has not exposed both validated distributions; rerun the failed publish job')


def missing_distributions(directory, tag, remote):
    version_key(tag)
    expected = {f'tidekeeper-{tag[1:]}.tar.gz', f'tidekeeper-{tag[1:]}-py3-none-any.whl'}
    validate_files(directory, expected)
    if set(remote) - expected:
        raise ValueError('PyPI contains unexpected files for this version')
    pending = []
    for name in sorted(expected):
        if name in remote:
            if digest(directory / name) != remote[name]:
                raise ValueError(f'PyPI already contains different bytes for {name}; refusing to overwrite or skip')
        else:
            pending.append(directory / name)
    return pending


def gh_json(endpoint):
    result = subprocess.run(['gh', 'api', endpoint], text=True, capture_output=True)
    if result.returncode:
        if 'HTTP 404' in result.stderr:
            return None
        raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout)


def check_github_assets(release):
    assets = release['assets']
    if {item['name'] for item in assets} != expected_assets() | {'SHA256SUMS'}:
        raise ValueError('GitHub release does not contain the complete platform asset set')
    if any(item['size'] <= 0 or item.get('state') != 'uploaded' for item in assets):
        raise ValueError('GitHub release has empty or unfinished assets')


def github_release(repository, tag):
    release = gh_json(f'repos/{repository}/releases/tags/{tag}')
    if release:
        return release
    # The by-tag endpoint only returns published releases. Drafts are visible
    # to our write token in the releases list and can be fetched by numeric ID.
    page = 1
    while True:
        releases = gh_json(f'repos/{repository}/releases?per_page=100&page={page}')
        if releases is None:
            raise ValueError('GitHub repository releases are inaccessible')
        for candidate in releases:
            if candidate['tag_name'] == tag:
                return gh_json(f'repos/{repository}/releases/{candidate["id"]}')
        if len(releases) < 100:
            return None
        page += 1


def _publish_validated_draft(repository, tag, release):
    check_github_assets(release)
    if not release['draft']:
        return
    latest = gh_json(f'repos/{repository}/releases/latest')
    promote = latest is None or version_key(tag) > version_key(latest['tag_name'])
    subprocess.run(['gh', 'release', 'edit', tag, '--repo', repository, '--draft=false',
                    '--latest' if promote else '--latest=false'], check=True)


def github_publish(repository, tag, directory, notes_file):
    """Stage, validate, and publish assets after the tag and PyPI files exist."""
    validate_files(directory, expected_assets() | {'SHA256SUMS'})
    title, _ = release_notes(Path.cwd(), tag)
    existing = github_release(repository, tag)
    if existing and not existing['draft']:
        check_github_assets(existing)
        print(f'{tag} is already public; leaving its assets intact')
        return
    if existing:
        subprocess.run(['gh', 'release', 'edit', tag, '--repo', repository,
                        '--title', title, '--notes-file', str(notes_file)], check=True)
    else:
        subprocess.run(['gh', 'release', 'create', tag, '--repo', repository, '--verify-tag', '--draft',
                        '--title', title, '--notes-file', str(notes_file)], check=True)
    subprocess.run(['gh', 'release', 'upload', tag, '--repo', repository, '--clobber',
                    *map(str, sorted(directory.iterdir()))], check=True)
    uploaded = github_release(repository, tag)
    if uploaded is None:
        raise ValueError('The uploaded GitHub draft is missing')
    _publish_validated_draft(repository, tag, uploaded)
    published = github_release(repository, tag)
    if published is None or published['draft']:
        raise ValueError('The GitHub release was not published')
    check_github_assets(published)
    print(f'Published https://github.com/{repository}/releases/tag/{tag}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('checksums', 'stage-pypi', 'verify-pypi', 'release'))
    parser.add_argument('--tag', required=True)
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--staging', type=Path)
    parser.add_argument('--repository')
    parser.add_argument('--notes', type=Path)
    args = parser.parse_args()
    version_key(args.tag)
    if args.command == 'checksums':
        validate_files(args.directory, expected_assets())
        content = ''.join(f'{digest(path)}  {path.name}\n' for path in sorted(args.directory.iterdir()))
        (args.directory / 'SHA256SUMS').write_text(content, encoding='utf-8')
    elif args.command == 'stage-pypi':
        pending = missing_distributions(args.directory, args.tag, read_pypi(args.tag))
        args.staging.mkdir(exist_ok=True)
        if any(args.staging.iterdir()):
            raise ValueError('PyPI staging directory must be empty')
        for path in pending:
            shutil.copy2(path, args.staging / path.name)
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as handle:
                handle.write(f'pending={str(bool(pending)).lower()}\n')
        print(f'{len(pending)} distributions need uploading')
    elif args.command == 'verify-pypi':
        wait_for_pypi(args.directory, args.tag)
    else:
        github_publish(args.repository, args.tag, args.directory, args.notes)


if __name__ == '__main__':
    main()
