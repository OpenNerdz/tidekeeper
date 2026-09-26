"""Shared HTTP backoff parsing for catalog and media requests."""
from datetime import timezone
from email.utils import parsedate_to_datetime
import math
import time

from .runtime import check_cancelled


def response_bytes(response, limit, label='Response'):
    """Read a streamed response with a bound on decompressed bytes."""
    try:
        length = int(response.headers.get('Content-Length', 0))
    except (TypeError, ValueError):
        length = 0
    if length > limit:
        raise ValueError(f'{label} is too large (limit {limit} bytes).')
    result = bytearray()
    for chunk in response.iter_content(chunk_size=64 * 1024):
        check_cancelled()
        if len(result) + len(chunk) > limit:
            raise ValueError(f'{label} is too large (limit {limit} bytes).')
        result.extend(chunk)
    return bytes(result)


def retry_delay(response, default, cap, minimum=0.0):
    """Accept Retry-After seconds or HTTP dates, with finite, bounded waits."""
    value = response.headers.get('Retry-After') if response is not None else None
    delay = default
    if value:
        try:
            parsed = float(value)
        except (TypeError, ValueError, OverflowError):
            try:
                date = parsedate_to_datetime(value)
                if date.tzinfo is None:
                    date = date.replace(tzinfo=timezone.utc)
                parsed = max(0.0, date.timestamp() - time.time())
            except (TypeError, ValueError, OverflowError, OSError):
                parsed = default
        if math.isfinite(parsed) and parsed >= 0:
            delay = parsed
    return max(minimum, min(delay, cap))
