from __future__ import annotations

import contextlib
import io
import os
import time
from dataclasses import dataclass, replace
from types import SimpleNamespace
from typing import Callable, Iterable, List, Optional

import aigpy

from .. import apiKey
from ..diagnostics import runDoctor
from ..enums import AudioQuality, Type, VideoQuality
from ..events import loginByConfig, logout, start, start_type
from ..lang.language import LANG
from ..paths import PATHS, openPath
from ..printf import VERSION
from ..settings import SETTINGS, TOKEN, syncPlaybackRateLimiter
from ..tidal import TIDAL_API
from ..updater import run_update


LogCallback = Optional[Callable[[str], None]]
