"""On-disk identities for resumable transfers and completed media."""
import hashlib
import json
import os
import shutil
from pathlib import Path

from .settings import _atomicWrite
from .runtime import check_cancelled


def file_digest(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            check_cancelled()
            digest.update(chunk)
    return digest.hexdigest()


def _read(path):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def prepare_transfer(path, urls):
    """Prepare resumable parts; return whether the assembled output is reusable."""
    # Include the complete URLs: query parameters can select different media.
    # A refreshed signature may restart a transfer, but must never mix streams.
    identity = hashlib.sha256(json.dumps(list(urls)).encode()).hexdigest()
    marker = path + '.source.json'
    state = _read(marker)
    matches = state.get('source') == identity
    if not matches:
        Path(path + '.download').unlink(missing_ok=True)
        parts = Path(path + '.parts')
        if parts.exists():
            shutil.rmtree(parts)
        _atomicWrite(marker, json.dumps({'source': identity, 'complete': False}))
    return matches and state.get('complete') is True


def complete_transfer(path):
    """Mark the assembled output only after it has been successfully replaced."""
    marker = path + '.source.json'
    state = _read(marker)
    state['complete'] = True
    _atomicWrite(marker, json.dumps(state))


def audio_identity(stream):
    return {'type': 'track', 'id': str(getattr(stream, 'trackid', '') or ''),
            'quality': getattr(stream, 'soundQuality', None), 'codec': getattr(stream, 'codec', None)}


def video_identity(video, quality):
    return {'type': 'video', 'id': str(video.id), 'quality': quality.name}


def record_completion(path, identity):
    stat = os.stat(path)
    if stat.st_size <= 0:
        raise OSError('Cannot finalize an empty media file')
    _atomicWrite(path + '.tidekeeper.json', json.dumps({
        'identity': identity, 'size': stat.st_size, 'sha256': file_digest(path),
    }))


def is_completed(path, identity):
    receipt = _read(path + '.tidekeeper.json')
    try:
        return (receipt.get('identity') == identity
                and os.path.getsize(path) > 0
                and receipt.get('size') == os.path.getsize(path)
                and receipt.get('sha256') == file_digest(path))
    except OSError:
        return False
