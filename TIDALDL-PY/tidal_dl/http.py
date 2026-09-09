"""Shared HTTP backoff parsing for catalog and media requests."""
from datetime import timezone
from email.utils import parsedate_to_datetime
import math
import time


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
