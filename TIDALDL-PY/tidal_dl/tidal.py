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
