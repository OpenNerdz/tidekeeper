"""Shared parsing for terminal batches and the desktop Links input."""
import os
from pathlib import Path

from .runtime import check_cancelled


def parse_direct_inputs(text, _seen_files=None):
    """Expand text lists without recursion; retain input order and deduplicate.

    Nested filenames are relative to the containing list. Real paths identify
    files so symlinks and lists that include themselves are read only once.
    """
    seen_files = set() if _seen_files is None else _seen_files
    seen = set()
    tokens = []
    pending = [(str(text or '').strip(), Path.cwd())]
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
            seen_files.add(path)
            try:
                content = path.read_text(encoding='utf-8-sig')
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
            seen.add(value)
            tokens.append(value)
    return tokens
