#!/usr/bin/env python
# -*- encoding: utf-8 -*-
'''
@File    :   tidal.py
@Time    :   2019/02/27
@Author  :   Yaronzz
@VERSION :   3.0
@Contact :   yaronhuang@foxmail.com
@Desc    :   tidal api
'''
import copy
import random
import re
import time
import base64
import json
import logging
from collections import OrderedDict
from threading import Lock
from typing import List
from xml.etree import ElementTree
from urllib.parse import unquote, urlparse

import aigpy
import requests

from .enums import AudioQuality, Type, VideoQuality
from .model import (
    Album,
    Artist,
    LoginKey,
    Lyrics,
    Mix,
    Playlist,
    SearchResult,
    StreamRespond,
    StreamUrl,
    Track,
    Video,
    VideoStreamUrl,
)
from .settings import SETTINGS, TOKEN, Settings, syncPlaybackRateLimiter

REQUEST_TIMEOUT = (5, 60)
API_BASE_PRIMARY = 'https://api.tidal.com/v1/'
API_BASE_LEGACY = 'https://api.tidalhifi.com/v1/'
PLAYBACK_ASSET_NOT_READY_ATTEMPTS = 6
RATE_LIMIT_MAX_ATTEMPTS = 3
RATE_LIMIT_MAX_WAIT_SECONDS = 90
# Keep short: signed CDN URLs often expire well under 10 minutes.
STREAM_CACHE_TTL_SECONDS = 90
STREAM_CACHE_MAX_ITEMS = 256
SEARCH_PAGE_SIZE = 50
SEARCH_MAX_ITEMS = 200
SEARCH_RESULT_TYPES = (Type.Artist, Type.Album, Type.Track, Type.Playlist, Type.Video)
SEARCH_BUCKETS = {
    Type.Track: 'tracks',
    Type.Video: 'videos',
    Type.Album: 'albums',
    Type.Artist: 'artists',
    Type.Playlist: 'playlists',
}


class RequestRateLimiter:
    def __init__(self, minInterval=1.0, jitter=0.5):
        self.minInterval = minInterval
        self.jitter = jitter
        self._adaptiveInterval = 0.0
        self._successes = 0
        self._lock = Lock()
        self._nextAllowed = 0.0

    def effectiveInterval(self):
        return max(self.minInterval, self._adaptiveInterval)

    def penalize(self, retryAfter=None):
        with self._lock:
            current = self.effectiveInterval()
            target = float(retryAfter) if retryAfter is not None else max(5.0, current * 2.0)
            self._adaptiveInterval = min(300.0, max(current, target))
            self._successes = 0
            self._nextAllowed = max(self._nextAllowed, time.monotonic() + self._adaptiveInterval)
            return self._adaptiveInterval

    def reward(self):
        with self._lock:
            if self._adaptiveInterval <= self.minInterval:
                self._adaptiveInterval = 0.0
                return self.effectiveInterval()
            self._successes += 1
            if self._successes >= 5:
                self._adaptiveInterval = max(self.minInterval, self._adaptiveInterval * 0.8)
                self._successes = 0
            return self.effectiveInterval()

    def wait(self):
        if self.effectiveInterval() <= 0:
            return 0.0

        with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._nextAllowed - now)
            base = now + delay
            self._nextAllowed = base + self.effectiveInterval() + random.uniform(0, self.jitter)

        if delay > 0:
            time.sleep(delay)
        return delay


PLAYBACK_RATE_LIMITER = RequestRateLimiter()


class TidalApiError(Exception):
    def __init__(self, message, statusCode=None, errorCodes=None):
        super().__init__(message)
        self.statusCode = statusCode
        self.errorCodes = errorCodes or []


class TidalStreamUnavailable(Exception):
    pass


class TidalAPI(object):
    def __init__(self):
        self.key = LoginKey()
        self.apiKey = {'clientId': 'fX2JxdmntZWK0ixT',
                       'clientSecret': '1Nn9AfDAjxrgJFJbKNWLeAyKGVGmINuXPPLHVXAvxAg='}
        self.session = requests.Session()
        # Retry transient connection failures at the transport level; HTTP
        # status handling (401/404/429) stays in the request helpers.
        adapter = requests.adapters.HTTPAdapter(pool_connections=8, pool_maxsize=16, max_retries=3)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.playbackRateLimiter = PLAYBACK_RATE_LIMITER
        self._playbackBlockedParams = set()
        self._streamCache = OrderedDict()
        self._streamCacheLock = Lock()
        self._tokenRefreshLock = Lock()
        # Serialize stream-manifest resolution so multi-thread downloads do not
        # stampede playback/OpenAPI endpoints.
        self._streamResolveLock = Lock()
        # Session caches that cut repeat catalog / Atmos-miss traffic.
        self._artistAlbumsCache = {}
        self._atmosAlbumTwinCache = {}
        self._atmosTrackTwinCache = {}
        self._atmosUnavailableTrackIds = set()
