"""Load the public supporter list without putting GitHub credentials in the app."""

from __future__ import annotations

import json
import re
from importlib import resources

import requests


SUPPORTERS_URL = (
    "https://raw.githubusercontent.com/OpenNerdz/tidekeeper/main/"
    "TIDALDL-PY/tidal_dl/gui_app/supporters.json"
)
_LOGIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")


def _normalise(payload) -> list[str]:
    if not isinstance(payload, list):
        raise ValueError("Supporter data is not a list.")
    names = []
    seen = set()
    for value in payload:
        if not isinstance(value, str) or not _LOGIN.fullmatch(value):
            continue
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            names.append(value)
    return names


def bundled_supporters() -> list[str]:
    """Return the release-time snapshot included with the application."""
    data = resources.files(__package__).joinpath("supporters.json").read_text(encoding="utf-8")
    return _normalise(json.loads(data))


def load_supporters() -> list[str]:
    """Return the current repository list, falling back to the bundled snapshot."""
    try:
        response = requests.get(
            SUPPORTERS_URL,
            headers={"User-Agent": "Tidekeeper"},
            timeout=(3, 8),
        )
        response.raise_for_status()
        return _normalise(response.json())
    except (requests.RequestException, ValueError, TypeError, json.JSONDecodeError):
        return bundled_supporters()
