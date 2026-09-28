"""Validate release files, resume matching PyPI uploads, and publish a complete draft."""

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
    version_key(tag)
    request = urllib.request.Request(f'https://pypi.org/pypi/tidekeeper/{tag[1:]}/json',
                                     headers={'User-Agent': 'Tidekeeper-release'})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return {}
        raise
    return {item['filename']: item['digests']['sha256'] for item in payload['urls']}


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


def github_draft(repository, tag, directory, notes_file):
    validate_files(directory, expected_assets() | {'SHA256SUMS'})
    title, _ = release_notes(Path.cwd(), tag)
    existing = gh_json(f'repos/{repository}/releases/tags/{tag}')
    if existing and not existing['draft']:
        check_github_assets(existing)
        # Never turn a public release back into a draft or replace its binaries.
        print(f'{tag} is already public; leaving its assets intact')
        return
    if not existing:
        subprocess.run(['gh', 'release', 'create', tag, '--repo', repository, '--verify-tag', '--draft',
                        '--title', title, '--notes-file', str(notes_file)], check=True)
    else:
        subprocess.run(['gh', 'release', 'edit', tag, '--repo', repository,
                        '--title', title, '--notes-file', str(notes_file)], check=True)
    subprocess.run(['gh', 'release', 'upload', tag, '--repo', repository, '--clobber',
                    *map(str, sorted(directory.iterdir()))], check=True)
    check_github_assets(gh_json(f'repos/{repository}/releases/tags/{tag}'))


def finalize(repository, tag):
    release = gh_json(f'repos/{repository}/releases/tags/{tag}')
    if not release:
        raise ValueError('The validated GitHub draft is missing')
    check_github_assets(release)
    if release['draft']:
        latest = gh_json(f'repos/{repository}/releases/latest')
        promote = latest is None or version_key(tag) > version_key(latest['tag_name'])
        subprocess.run(['gh', 'release', 'edit', tag, '--repo', repository, '--draft=false',
                        '--latest' if promote else '--latest=false'], check=True)
    print(f'Published https://github.com/{repository}/releases/tag/{tag}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('checksums', 'stage-pypi', 'verify-pypi', 'draft', 'finalize'))
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
        pending = missing_distributions(args.directory, args.tag, pypi_files(args.tag))
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
        for attempt in range(6):
            if not missing_distributions(args.directory, args.tag, pypi_files(args.tag)):
                print('Both PyPI distribution hashes match the validated build')
                return
            if attempt < 5:
                time.sleep(10)
        raise RuntimeError('PyPI has not exposed both validated distributions; rerun the failed publish job')
    elif args.command == 'draft':
        github_draft(args.repository, args.tag, args.directory, args.notes)
    else:
        finalize(args.repository, args.tag)


if __name__ == '__main__':
    main()
