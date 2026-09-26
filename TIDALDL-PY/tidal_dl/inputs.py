"""Shared parsing for terminal batches and the desktop Links input."""
import os
from pathlib import Path

from .runtime import check_cancelled

MAX_LIST_BYTES = 8 * 1024 * 1024
MAX_LIST_FILES = 4096
MAX_INPUTS = 50000


def parse_direct_inputs(text, _seen_files=None):
    """Expand text lists without recursion; retain input order and deduplicate.

    Nested filenames are relative to the containing list. Real paths identify
    files so symlinks and lists that include themselves are read only once.
    """
    seen_files = set() if _seen_files is None else _seen_files
    seen = set()
    tokens = []
    pending = [(str(text or '').strip(), Path.cwd())]
    total_bytes = len(pending[0][0].encode('utf-8'))
    if total_bytes > MAX_LIST_BYTES:
        raise ValueError('URL list is too large (maximum 8 MiB).')
    while pending:
        check_cancelled()
        value, directory = pending.pop()
        if not value:
            continue
        lines = value.splitlines()
        if len(lines) > 1:
            pending.extend((line.strip(), directory) for line in reversed(lines))
            continue
        candidate = directory / os.path.expanduser(value)
        try:
            is_file = candidate.is_file()
        except OSError:
            is_file = False
        if is_file:
            path = candidate.resolve()
            if path in seen_files:
                continue
            if len(seen_files) >= MAX_LIST_FILES:
                raise ValueError('URL list includes too many files.')
            seen_files.add(path)
            try:
                with path.open('rb') as source:
                    data = source.read(MAX_LIST_BYTES - total_bytes + 1)
                total_bytes += len(data)
                if total_bytes > MAX_LIST_BYTES:
                    raise ValueError('URL lists exceed the total size limit (8 MiB).')
                content = data.decode('utf-8-sig')
            except (OSError, UnicodeError) as error:
                raise ValueError(f'Unable to read URL list {path}: {error}') from error
            pending.extend((line.strip(), path.parent) for line in reversed(content.splitlines()))
            continue
        if value[0] in '#[{':
            continue
        parts = [part.strip() for line in value.splitlines() for part in line.split(',') if part.strip()]
        if len(parts) != 1 or (parts and parts[0] != value):
            pending.extend((part, directory) for part in reversed(parts))
            continue
        words = value.split()
        if len(words) > 1:
            pending.extend((word, directory) for word in reversed(words))
            continue
        if value not in seen:
            if len(tokens) >= MAX_INPUTS:
                raise ValueError('URL list contains too many items.')
            seen.add(value)
            tokens.append(value)
    return tokens
