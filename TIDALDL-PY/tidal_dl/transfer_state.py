"""On-disk identities for resumable transfers and completed media."""
import hashlib
import json
import os
import shutil
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .settings import _atomicWrite
from .runtime import check_cancelled


def file_digest(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            check_cancelled()
            digest.update(chunk)
    return digest.hexdigest()


def file_fingerprint(path):
    """Hash small samples across a file for fast routine completion checks."""
    size = os.path.getsize(path)
    digest = hashlib.sha256()
    sample_size = 64 * 1024
    offsets = sorted({0, max(0, size // 2 - sample_size // 2), max(0, size - sample_size)})
    with open(path, 'rb') as source:
        for offset in offsets:
            check_cancelled()
            source.seek(offset)
            digest.update(str(offset).encode('ascii'))
            digest.update(source.read(sample_size))
    return digest.hexdigest()


def _read(path):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


AUTH_QUERY_KEYS = {
    'authorization', 'expires', 'key-pair-id', 'policy', 'signature', 'sig',
    'token', 'x-amz-algorithm', 'x-amz-content-sha256', 'x-amz-credential',
    'x-amz-date', 'x-amz-expires', 'x-amz-security-token', 'x-amz-signature',
    'x-amz-signedheaders', 'x-goog-algorithm', 'x-goog-credential',
    'x-goog-date', 'x-goog-expires', 'x-goog-signature', 'x-goog-signedheaders',
}


def _stable_url(url):
    """Remove only known expiring authorization fields from a media URL."""
    parsed = urlsplit(str(url))
    query = [
        (key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in AUTH_QUERY_KEYS
    ]
    host = (parsed.hostname or '').lower()
    if parsed.port:
        host += f':{parsed.port}'
    return urlunsplit((parsed.scheme.lower(), host, parsed.path, urlencode(sorted(query)), ''))


def prepare_transfer(path, urls, source_identity=None):
    """Prepare resumable parts; return whether the assembled output is reusable."""
    # Keep media-selecting query fields, but ignore known expiring signatures so
    # a renewed CDN token can resume the same immutable track representation.
    source = {
        'media': source_identity,
        'urls': [_stable_url(url) for url in urls],
    }
    identity = hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()
    marker = path + '.source.json'
    state = _read(marker)
    matches = state.get('source') == identity
    if not matches:
        Path(path + '.download').unlink(missing_ok=True)
        parts = Path(path + '.parts')
        if parts.exists():
            shutil.rmtree(parts)
        _atomicWrite(marker, json.dumps({'source': identity, 'complete': False}))
    if not matches or state.get('complete') is not True:
        return False

    # A completed transfer can be reused without another CDN size probe, but
    # only when the local object still has the exact size recorded at commit.
    # Older markers did not record a size and are conservatively downloaded
    # again once, then upgraded by ``complete_transfer`` below.
    try:
        recorded_size = int(state.get('size', 0))
        return recorded_size > 0 and os.path.getsize(path) == recorded_size
    except (OSError, TypeError, ValueError):
        return False


def complete_transfer(path):
    """Mark the assembled output only after it has been successfully replaced."""
    marker = path + '.source.json'
    state = _read(marker)
    size = os.path.getsize(path)
    if size <= 0:
        raise OSError('Cannot complete an empty transfer')
    state['complete'] = True
    state['size'] = size
    _atomicWrite(marker, json.dumps(state))


def audio_identity(stream):
    # Keep this stable for receipts written by older Tidekeeper releases.
    return {'type': 'track', 'id': str(getattr(stream, 'trackid', '') or ''),
            'quality': getattr(stream, 'soundQuality', None), 'codec': getattr(stream, 'codec', None)}


def video_identity(video, quality):
    return {'type': 'video', 'id': str(video.id), 'quality': quality.name}


def record_completion(path, identity, metadata_complete=True, media_facts=None):
    stat = os.stat(path)
    if stat.st_size <= 0:
        raise OSError('Cannot finalize an empty media file')
    _atomicWrite(path + '.tidekeeper.json', json.dumps({
        'identity': identity, 'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
        'sha256': file_digest(path), 'fingerprint': file_fingerprint(path),
        'media': media_facts or {},
        'metadata_complete': metadata_complete,
    }))


def completion_state(path, identity, verify=False):
    """Return (media_complete, metadata_complete) for a completion receipt."""
    receipt = _read(path + '.tidekeeper.json')
    try:
        stat = os.stat(path)
        if receipt.get('identity') != identity or stat.st_size <= 0 or receipt.get('size') != stat.st_size:
            return False, False
        unchanged = receipt.get('mtime_ns') == stat.st_mtime_ns
        fingerprint = receipt.get('fingerprint')
        if fingerprint:
            unchanged = unchanged and fingerprint == file_fingerprint(path)
        if verify or not unchanged or not fingerprint:
            unchanged = receipt.get('sha256') == file_digest(path)
        if not unchanged:
            return False, False
        return True, receipt.get('metadata_complete', True) is True
    except OSError:
        return False, False


def is_completed(path, identity, verify=False):
    media_complete, metadata_complete = completion_state(path, identity, verify=verify)
    return media_complete and metadata_complete
