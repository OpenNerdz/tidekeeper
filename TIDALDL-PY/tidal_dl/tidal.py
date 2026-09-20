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
from .runtime import print, check_cancelled, DownloadCancelled, sleep as cancellable_sleep, report_warning
import logging
import math
from collections import OrderedDict
from threading import Lock, RLock
from urllib.parse import unquote, urlparse

import aigpy
import requests

from . import apiKey as apiKeys
from .enums import AudioQuality, Type, VideoQuality, audio_quality_fallbacks, playback_quality_priority
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
from .manifests import ProtectedManifestError, best_dash_representation, dash_segments, hls_variants
from .http import retry_delay
from .settings import SETTINGS, TOKEN, Settings, syncPlaybackRateLimiter

REQUEST_TIMEOUT = (5, 60)
LOGOUT_TIMEOUT = (3, 10)
API_BASE_PRIMARY = 'https://api.tidal.com/v1/'
API_BASE_LEGACY = 'https://api.tidalhifi.com/v1/'
CATALOG_MAX_ATTEMPTS = 3
PLAYBACK_ASSET_NOT_READY_ATTEMPTS = 6
AUTH_MAX_ATTEMPTS = 3
# HTTP 429 retries never consume the attempt budget above. Instead the total
# time spent waiting on rate limits for one logical request is capped here.
RATE_LIMIT_MAX_WAIT_SECONDS = 90
# Keep short: signed CDN URLs often expire well under 10 minutes.
STREAM_CACHE_TTL_SECONDS = 90
STREAM_CACHE_MAX_ITEMS = 256
PLAYBACK_BLOCK_TTL_SECONDS = 300
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
            cancellable_sleep(delay)
        return delay


PLAYBACK_RATE_LIMITER = RequestRateLimiter()


class RateLimitWaitBudget:
    """Cumulative HTTP 429 back-off allowance for a single logical request.

    Rate-limited responses are retried without consuming the caller's normal
    attempt budget; instead the total time slept is capped so a persistently
    throttled client eventually fails instead of hanging forever.
    """

    def __init__(self, maxWaitSeconds=RATE_LIMIT_MAX_WAIT_SECONDS):
        self.maxWaitSeconds = maxWaitSeconds
        self.waited = 0.0
        self.attempts = 0

    def allows(self, delay):
        return math.isfinite(delay) and delay > 0 and self.waited + delay <= self.maxWaitSeconds

    def record(self, delay):
        self.waited += delay
        self.attempts += 1


class TidalApiError(Exception):
    def __init__(self, message, statusCode=None, errorCodes=None):
        super().__init__(message)
        self.statusCode = statusCode
        self.errorCodes = errorCodes or []


class TidalPlaybackClientError(TidalApiError):
    """A playback service rejected the client; login validity is unproven."""


class TidalStreamUnavailable(Exception):
    pass


class TidalAPI(object):
    def __init__(self):
        self.key = LoginKey()
        self.apiKey = apiKeys.getItem(apiKeys.getDefaultIndex())
        self.session = requests.Session()
        # Retry transient connection failures at the transport level; HTTP
        # status handling (401/404/429) stays in the request helpers.
        adapter = requests.adapters.HTTPAdapter(pool_connections=8, pool_maxsize=16, max_retries=3)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.playbackRateLimiter = PLAYBACK_RATE_LIMITER
        self._playbackBlockedParams = {}
        self._streamCache = OrderedDict()
        self._streamCacheLock = Lock()
        self._tokenRefreshLock = Lock()
        self._authStateLock = RLock()
        self._sessionGeneration = 0
        # Serialize stream-manifest resolution so multi-thread downloads do not
        # stampede playback/OpenAPI endpoints.
        self._streamResolveLock = Lock()
        # Session caches that cut repeat catalog / Atmos-miss traffic.
        self._artistAlbumsCache = {}
        self._atmosAlbumTwinCache = {}
        self._atmosTrackTwinCache = {}
        self._atmosUnavailableTrackIds = set()

    def clearSession(self):
        """Invalidate pending logins and all account/client-dependent caches."""
        with self._authStateLock:
            self._sessionGeneration += 1
            self.key = LoginKey()
            self.clearSessionCaches()

    def clearSavedSession(self):
        """Remove a persisted login that cannot be used by the active client."""
        with self._authStateLock:
            self.clearSession()
            TOKEN.userid = None
            TOKEN.countryCode = None
            TOKEN.clientId = None
            TOKEN.accessToken = None
            TOKEN.refreshToken = None
            TOKEN.expiresAfter = 0
            TOKEN.save()

    def logoutSavedSession(self, revoke=None):
        """Clear local state immediately, then revoke the captured session.

        The desktop can supply a dispatcher to run revocation in a worker.
        That worker must never clear local state belonging to a later login.
        """
        access_token = self.key.accessToken or getattr(TOKEN, 'accessToken', None)
        self.clearSavedSession()
        if not access_token:
            return False
        return (revoke or self.revokeSession)(access_token)

    def revokeSession(self, access_token):
        """Best-effort remote revocation without changing current login state."""
        revoked = False
        try:
            if access_token:
                response = self.session.post(
                    'https://api.tidal.com/v1/logout',
                    headers={'authorization': f'Bearer {access_token}'},
                    timeout=LOGOUT_TIMEOUT,
                )
                try:
                    revoked = response.status_code in (200, 204, 401)
                    if not revoked:
                        logging.warning('TIDAL session revocation returned HTTP %s.', response.status_code)
                finally:
                    response.close()
        except requests.RequestException as error:
            logging.warning('Unable to revoke the TIDAL session remotely: %s', type(error).__name__)
        return revoked

    def clearSavedSessionIfClientChanged(self):
        """Discard tokens minted for a different (or unknown legacy) client."""
        if aigpy.string.isNull(getattr(TOKEN, 'accessToken', None)):
            return False
        active_client_id = str(self.apiKey.get('clientId') or '')
        saved_client_id = str(getattr(TOKEN, 'clientId', None) or '')
        if not active_client_id or saved_client_id == active_client_id:
            return False
        self.logoutSavedSession()
        return True

    def clearSessionCaches(self):
        with self._streamCacheLock:
            self._streamCache.clear()
        self._playbackBlockedParams.clear()
        self._artistAlbumsCache.clear()
        self._atmosAlbumTwinCache.clear()
        self._atmosTrackTwinCache.clear()
        self._atmosUnavailableTrackIds.clear()

    def __responseBody__(self, response):
        try:
            body = response.json()
            return body if isinstance(body, dict) else {}
        except ValueError:
            return {}

    def __isAssetNotReady__(self, response):
        if response is None or response.status_code != 401:
            return False
        body = self.__responseBody__(response)
        sub_status = body.get('subStatus', body.get('sub_status'))
        if sub_status == 4005 or str(sub_status) == '4005':
            return True
        message = str(body.get('userMessage', '')).lower()
        return 'not ready for playback' in message or 'asset is not ready' in message

    def __isPlaybackPath__(self, path):
        return 'playbackinfo' in (path or '')

    def __shouldTryLegacyApiHost__(self, path, error):
        if self.__isPlaybackPath__(path) or self.__isStaleClientError__(error):
            return False
        if isinstance(error, TidalApiError):
            return error.statusCode in (404, 500, 502, 503, 504)
        return True

    def __responseErrorCodes__(self, response):
        try:
            data = response.json()
        except ValueError:
            return []

        codes = []
        if isinstance(data, dict):
            errors = data.get('errors')
            if isinstance(errors, list):
                codes += [
                    item.get('code') for item in errors
                    if isinstance(item, dict) and item.get('code')
                ]
            if data.get('code'):
                codes.append(data.get('code'))
            for key in ('sub_status', 'subStatus'):
                if data.get(key):
                    codes.append(str(data.get(key)))
        return codes

    def __responseText__(self, response):
        text = getattr(response, 'text', None)
        if text:
            return str(text)
        content = getattr(response, 'content', b'') or b''
        if isinstance(content, bytes):
            return content.decode('utf-8', 'replace')
        return str(content)

    def __httpError__(self, action, response):
        detail = self.__responseText__(response)[:200].replace("\n", " ")
        return TidalApiError(
            f"{action} failed: HTTP {response.status_code} {detail}",
            response.status_code,
            self.__responseErrorCodes__(response),
        )

    def __refreshSavedAccessToken__(self):
        if aigpy.string.isNull(getattr(TOKEN, 'refreshToken', None)):
            return False

        access_token_before_wait = self.key.accessToken
        with self._tokenRefreshLock:
            # Another worker may have refreshed while this request waited.
            if (
                not aigpy.string.isNull(getattr(TOKEN, 'accessToken', None))
                and TOKEN.accessToken != access_token_before_wait
            ):
                self.key.userId = TOKEN.userid
                self.key.countryCode = TOKEN.countryCode
                self.key.accessToken = TOKEN.accessToken
                self.key.refreshToken = TOKEN.refreshToken
                return True

            try:
                if not self.refreshAccessToken(TOKEN.refreshToken):
                    return False

                TOKEN.userid = self.key.userId
                TOKEN.countryCode = self.key.countryCode
                TOKEN.clientId = self.apiKey.get('clientId')
                TOKEN.accessToken = self.key.accessToken
                TOKEN.refreshToken = self.key.refreshToken
                TOKEN.expiresAfter = time.time() + int(self.key.expiresIn)
                TOKEN.save()
                return True
            except (KeyError, TypeError, ValueError, OSError, requests.RequestException) as error:
                logging.info("Unable to refresh saved access token: %s", error)
                return False

    def __requestIntervalSeconds__(self):
        if SETTINGS.downloadDelay is False:
            return 0.0
        return max(0.0, float(getattr(SETTINGS, 'requestIntervalSeconds', 1.0) or 0.0))

    def __waitForStreamRequestQuota__(self):
        if SETTINGS.downloadDelay is False:
            return
        syncPlaybackRateLimiter()
        self.playbackRateLimiter.wait()

    def __waitForCatalogRequestQuota__(self):
        """Pace catalog calls only while adaptive backoff is elevated after 429s.

        Normal search stays snappy; after rate limits, catalog traffic cools down
        with the same shared limiter used for playback/manifest requests.
        """
        if SETTINGS.downloadDelay is False:
            return
        if not getattr(SETTINGS, 'adaptiveRateLimit', True):
            return
        syncPlaybackRateLimiter()
        limiter = self.playbackRateLimiter
        if limiter.effectiveInterval() <= max(limiter.minInterval, 0.0):
            return
        limiter.wait()

    def __applyRateLimitPenalty__(self, response, attempt):
        delay = self.__retryAfter__(response, attempt)
        if getattr(SETTINGS, 'adaptiveRateLimit', True):
            penalize = getattr(self.playbackRateLimiter, 'penalize', None)
            if penalize is not None:
                delay = penalize(delay)
        return delay

    def __backOffForRateLimit__(self, action, response, budget):
        """Sleep after an HTTP 429, or raise once the cumulative wait cap is reached.

        Shared by the catalog and OpenAPI manifest request loops so both apply
        the same adaptive penalty, logging, and wait-cap semantics.
        """
        delay = self.__applyRateLimitPenalty__(response, budget.attempts)
        if not budget.allows(delay):
            raise self.__httpError__(action, response)
        print(f"Too many requests, automatically waiting {delay:g} seconds before retry.")
        response.close()
        cancellable_sleep(delay)
        budget.record(delay)

    def __backOffForAssetNotReady__(self, response, attempt):
        """Sleep with a linear, capped delay while TIDAL finishes preparing an asset."""
        delay = min(5 * (attempt + 1), 30)
        print(f"Asset not ready for playback, waiting {delay:g} seconds before retry.")
        response.close()
        cancellable_sleep(delay)

    def __rewardStreamRequest__(self):
        if not getattr(SETTINGS, 'adaptiveRateLimit', True):
            return
        reward = getattr(self.playbackRateLimiter, 'reward', None)
        if reward is not None:
            reward()

    def __isPlaybackBlockedError__(self, error):
        if not isinstance(error, TidalApiError):
            return False
        # Generic 403/404 responses can be track- or endpoint-specific. Only an
        # explicit client capability error is safe to cache across tracks.
        return 'CLIENT_NOT_ENTITLED' in error.errorCodes

    def __isNonRetryableTidalApiError__(self, error, playbackRequest=False):
        if not isinstance(error, TidalApiError):
            return False
        if error.statusCode == 429:
            # A 429 reaches this handler only after its wait budget is spent.
            return True
        if self.__isPlaybackBlockedError__(error):
            return True
        if playbackRequest and error.statusCode == 401:
            return True
        return error.statusCode in (400, 403, 404, 405, 406, 410, 422)

    def __isStaleClientError__(self, error):
        if isinstance(error, TidalApiError) and any(str(code) == '4022' for code in error.errorCodes):
            return True
        text = str(error or "").lower()
        return 'client referenced in the request' in text or 'substatus 4022' in text

    def __isStaleClientResponse__(self, response):
        if response is None or response.status_code != 404:
            return False
        body = self.__responseBody__(response)
        if any(str(code) == '4022' for code in self.__responseErrorCodes__(response)):
            return True
        return 'client referenced in the request' in str(body.get('userMessage', '')).lower()

    def __playbackClientError__(self, endpoint, quality):
        # Do not include response bodies, bearer tokens, or OAuth secrets in
        # diagnostics. A playback-only 4022 does not prove the login is stale.
        client = self.apiKey.get('platform') or 'unknown'
        country = self.key.countryCode or 'unknown'
        return TidalPlaybackClientError(
            f"Playback client rejected (HTTP 404, subStatus 4022; endpoint={endpoint}; "
            f"client={client}; country={country}; quality={quality}). "
            "Your saved login has been kept. This client, account, or requested quality "
            "may be unavailable for playback; try HiFi or configure a quality-priority order. "
            "If it persists, include these diagnostics in an issue report.",
            404,
            ['4022'],
        )

    def __markPlaybackParamBlocked__(self, audio_param, error):
        if not audio_param or not isinstance(error, TidalApiError):
            return
        if self.__isStaleClientError__(error):
            # A 4022 does not prove this quality is unavailable for every track.
            # Keep later downloads from inheriting a playback-specific failure.
            return
        # Only cache client-level capability blocks. A track-specific 403
        # (for example PREREQUISITE_MISSING) must not disable the playback
        # API for every other track in this session.
        if 'CLIENT_NOT_ENTITLED' in error.errorCodes:
            self._playbackBlockedParams[audio_param] = time.monotonic() + PLAYBACK_BLOCK_TTL_SECONDS

    def __isPlaybackParamBlocked__(self, audio_param):
        expires = self._playbackBlockedParams.get(audio_param, 0)
        if expires > time.monotonic():
            return True
        self._playbackBlockedParams.pop(audio_param, None)
        return False

    def __isRateLimitError__(self, error):
        if isinstance(error, TidalApiError) and error.statusCode is not None:
            return error.statusCode == 429
        text = str(error or "").lower()
        return any(token in text for token in ("429", "too many requests", "rate limit"))

    def __shouldSkipOpenApiFallback__(self, error):
        return self.__isRateLimitError__(error) or (
            self.__isStaleClientError__(error) and not isinstance(error, TidalPlaybackClientError)
        )

    def __retryAfter__(self, response, attempt):
        return retry_delay(response, default=min(5 * (attempt + 1), 30), cap=300,
                           minimum=max(1.0, self.__requestIntervalSeconds__()))

    def __get__(self, path, params=None, urlpre=None):
        if urlpre is not None:
            return self.__getOnce__(path, params, urlpre)
        try:
            return self.__getOnce__(path, params, API_BASE_PRIMARY)
        except DownloadCancelled:
            raise
        except Exception as e:
            if self.__shouldTryLegacyApiHost__(path, e):
                return self.__getOnce__(path, params, API_BASE_LEGACY)
            raise

    def __getOnce__(self, path, params=None, urlpre=API_BASE_PRIMARY):
        params = {} if params is None else dict(params)
        params['countryCode'] = self.key.countryCode
        errmsg = "Get operation err!"
        respond = None
        lastError = None
        refreshedToken = False
        url = urlpre + path
        playbackRequest = self.__isPlaybackPath__(path)
        maxAttempts = PLAYBACK_ASSET_NOT_READY_ATTEMPTS if playbackRequest else CATALOG_MAX_ATTEMPTS
        index = 0
        rateLimitBudget = RateLimitWaitBudget()
        while index < maxAttempts:
            consumeAttempt = True
            check_cancelled()
            try:
                header = {'authorization': f'Bearer {self.key.accessToken}'}
                if playbackRequest:
                    self.__waitForStreamRequestQuota__()
                else:
                    # Only engages after a 429 raised the adaptive interval.
                    self.__waitForCatalogRequestQuota__()

                respond = self.session.get(url, headers=header, params=params, timeout=REQUEST_TIMEOUT)

                if respond.status_code == 429:
                    # Always apply adaptive penalty (catalog and playback) so one
                    # storm cools the whole client, not only stream endpoints.
                    self.__backOffForRateLimit__("Get operation", respond, rateLimitBudget)
                    consumeAttempt = False
                    continue

                if respond.status_code == 401 and self.__isAssetNotReady__(respond):
                    self.__backOffForAssetNotReady__(respond, index)
                    continue

                if respond.status_code == 401 and not refreshedToken and self.__refreshSavedAccessToken__():
                    refreshedToken = True
                    continue

                if respond.status_code == 404 and self.__isStaleClientResponse__(respond):
                    if playbackRequest:
                        raise self.__playbackClientError__(
                            path, params.get('audioquality') or params.get('videoquality') or 'unknown',
                        )
                    if not refreshedToken and self.__refreshSavedAccessToken__():
                        refreshedToken = True
                        continue
                    error = self.__httpError__("Get operation", respond)
                    self.clearSavedSession()
                    raise TidalApiError(
                        "Get operation failed: the saved login session references an API client "
                        "that no longer exists (HTTP 404, subStatus 4022). "
                        "The unusable session was cleared; please log in again.",
                        404,
                        error.errorCodes,
                    )

                if respond.status_code != 200:
                    raise self.__httpError__("Get operation", respond)

                try:
                    result = json.loads(respond.text)
                except (TypeError, ValueError) as error:
                    raise TidalApiError(
                        "Get operation failed: TIDAL returned invalid JSON.",
                        respond.status_code,
                    ) from error
                if not isinstance(result, dict):
                    raise TidalApiError(
                        "Get operation failed: TIDAL returned an invalid JSON payload.",
                        respond.status_code,
                    )
                if 'status' not in result:
                    if playbackRequest:
                        self.__rewardStreamRequest__()
                    return result

                if 'userMessage' in result and result['userMessage'] is not None:
                    errmsg += result['userMessage']
                break
            except TidalApiError as e:
                if self.__isNonRetryableTidalApiError__(e, playbackRequest) or index >= maxAttempts - 1:
                    raise e
                lastError = e
                if e.statusCode in (500, 502, 503, 504):
                    cancellable_sleep(self.__retryAfter__(respond, index))
            except DownloadCancelled:
                raise
            except Exception as e:
                lastError = e
                if index >= maxAttempts - 1 and respond is not None:
                    errmsg += respond.text
            finally:
                if respond is not None:
                    respond.close()
                if consumeAttempt:
                    index += 1

        if respond is not None and self.__isAssetNotReady__(respond):
            body = self.__responseBody__(respond)
            message = body.get('userMessage') or 'Asset is not ready for playback'
            raise Exception(f"{errmsg}{message}") from lastError
        if lastError is not None and aigpy.string.isNull(errmsg.replace("Get operation err!", "")):
            raise Exception(f"{errmsg} {lastError}") from lastError
        raise Exception(errmsg) from lastError

    def __getPlaybackData__(self, item_id, params, media='tracks'):
        params = dict(params or {})
        params['prefetch'] = 'false'
        endpoints = [
            (API_BASE_PRIMARY, f'{media}/{item_id}/playbackinfopostpaywall/v4'),
            (API_BASE_PRIMARY, f'{media}/{item_id}/playbackinfopostpaywall'),
            (API_BASE_LEGACY, f'{media}/{item_id}/playbackinfopostpaywall/v4'),
            (API_BASE_LEGACY, f'{media}/{item_id}/playbackinfopostpaywall'),
        ]
        last_error = None
        for base, path in endpoints:
            try:
                return self.__getOnce__(path, params, base)
            except DownloadCancelled:
                raise
            except Exception as e:
                last_error = e
                logging.debug("Playback request failed for %s%s: %s", base, path, e)
                # A v4 404 must fall through to the unversioned and legacy
                # endpoints. Stop only for account/client, auth, or rate-limit
                # failures that cannot be repaired by changing the route.
                if (self.__isPlaybackBlockedError__(e)
                        or self.__isRateLimitError__(e)
                        or self.__isStaleClientError__(e)
                        or (isinstance(e, TidalApiError) and e.statusCode == 401)):
                    break
        raise last_error

    def __getItems__(self, path, params=None):
        params = {} if params is None else dict(params)
        params['limit'] = 50
        params['offset'] = 0
        total = 0
        ret = []
        while True:
            data = self.__get__(path, params)
            if 'totalNumberOfItems' in data:
                total = data['totalNumberOfItems']
            ret += data["items"]
            num = len(data["items"])
            if num < 50 or (total > 0 and len(ret) >= total):
                break
            params['offset'] += num
        return ret

    def __getResolutionList__(self, url):
        response = self.session.get(url, timeout=REQUEST_TIMEOUT)
        try:
            response.raise_for_status()
            ret = []
            for width, height, codec, location in hls_variants(response.content, url):
                stream = VideoStreamUrl()
                stream.codec = codec
                stream.m3u8Url = location
                stream.resolution = f'{width}x{height}'
                stream.resolutions = [str(width), str(height)]
                ret.append(stream)
            if not ret:
                raise TidalStreamUnavailable('No video variants found in the HLS manifest.')
            return ret
        finally:
            response.close()

    def __post__(self, path, data, auth=None, urlpre='https://auth.tidal.com/v1/oauth2'):
        url = urlpre + path
        lastAttempt = AUTH_MAX_ATTEMPTS - 1
        for attempt in range(AUTH_MAX_ATTEMPTS):
            check_cancelled()
            response = None
            try:
                response = self.session.post(url, data=data, auth=auth, timeout=REQUEST_TIMEOUT)
                try:
                    result = response.json()
                except ValueError as error:
                    detail = self.__responseText__(response)[:200].replace("\n", " ")
                    if response.status_code < 500:
                        raise TidalApiError(
                            f"Auth operation failed: HTTP {response.status_code} {detail}",
                            response.status_code,
                        ) from error
                    raise requests.HTTPError(
                        f"Unexpected HTTP {response.status_code} response from Tidal auth endpoint: {detail}",
                        response=response,
                    ) from error

                if not isinstance(result, dict):
                    raise TidalApiError("Auth endpoint returned an invalid JSON payload.", response.status_code)
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt == lastAttempt:
                        raise self.__httpError__("Auth operation", response)
                    delay = self.__retryAfter__(response, attempt)
                    response.close()
                    cancellable_sleep(delay)
                    continue
                # OAuth errors are valid JSON responses and callers interpret
                # authorization_pending and invalid_grant themselves.
                return result
            except TidalApiError:
                raise
            except requests.RequestException:
                if attempt == lastAttempt:
                    raise
                cancellable_sleep(min(2 ** attempt, 10))
            finally:
                if response is not None:
                    response.close()
        raise TidalApiError("Auth operation failed after retries.")

    def getDeviceCode(self) -> str:
        data = {
            'client_id': self.apiKey['clientId'],
            'scope': 'r_usr w_usr w_sub'
        }
        if not aigpy.string.isNull(self.apiKey.get('clientSecret')):
            data['client_secret'] = self.apiKey['clientSecret']
        result = self.__post__('/device_authorization', data)
        if 'status' in result and result['status'] != 200:
            raise Exception("Device authorization failed. Please choose another apikey.")

        self.key.deviceCode = result['deviceCode']
        self.key.userCode = result['userCode']
        self.key.verificationUrl = result['verificationUri']
        self.key.authCheckTimeout = result['expiresIn']
        self.key.authCheckInterval = result['interval']
        return "https://" + self.key.verificationUrl + "/" + self.key.userCode

    def checkAuthStatus(self) -> bool:
        generation = self._sessionGeneration
        data = {
            'client_id': self.apiKey['clientId'],
            'device_code': self.key.deviceCode,
            'grant_type': 'urn:ietf:params:oauth:grant-type:device_code',
            'scope': 'r_usr w_usr w_sub'
        }
        if not aigpy.string.isNull(self.apiKey.get('clientSecret')):
            data['client_secret'] = self.apiKey['clientSecret']
        result = self.__post__('/token', data)
        error = result.get('error')
        if error in ('authorization_pending', 'slow_down'):
            return False
        if error in ('expired_token', 'access_denied'):
            raise Exception("Login code expired. Start login again.")
        if 'status' in result and result['status'] != 200:
            if result['status'] == 400 and result.get('sub_status') == 1002:
                return False
            elif result.get('error') in ('authorization_pending', 'slow_down'):
                return False
            else:
                raise Exception("Error while checking for authorization. Trying again...")

        # if auth is successful:
        with self._authStateLock:
            if generation != self._sessionGeneration:
                return False
            self.clearSessionCaches()
            self.key.userId = result['user']['userId']
            self.key.countryCode = result['user']['countryCode']
            self.key.accessToken = result['access_token']
            self.key.refreshToken = result['refresh_token']
            self.key.expiresIn = result['expires_in']
        return True

    def verifyAccessToken(self, accessToken) -> bool:
        header = {'authorization': f'Bearer {accessToken}'}
        response = None
        try:
            response = self.session.get('https://api.tidal.com/v1/sessions', headers=header, timeout=REQUEST_TIMEOUT)
            if response.status_code in (401, 403):
                return False
            if response.status_code != 200:
                raise self.__httpError__('Session verification', response)
            result = response.json()
            return (isinstance(result, dict) and result.get('status', 200) == 200
                    and result.get('userId') is not None and bool(result.get('countryCode')))
        except ValueError as error:
            raise TidalApiError('Session verification returned invalid JSON.') from error
        finally:
            if response is not None:
                response.close()

    def refreshAccessToken(self, refreshToken) -> bool:
        generation = self._sessionGeneration
        data = {
            'client_id': self.apiKey['clientId'],
            'refresh_token': refreshToken,
            'grant_type': 'refresh_token',
            'scope': 'r_usr w_usr w_sub'
        }
        if not aigpy.string.isNull(self.apiKey.get('clientSecret')):
            data['client_secret'] = self.apiKey['clientSecret']
        result = self.__post__('/token', data)
        if result.get('error') or ('status' in result and result['status'] != 200):
            return False

        # if auth is successful:
        with self._authStateLock:
            if generation != self._sessionGeneration:
                return False
            self.key.userId = result['user']['userId']
            self.key.countryCode = result['user']['countryCode']
            self.key.accessToken = result['access_token']
            self.key.refreshToken = result.get('refresh_token', refreshToken)
            self.key.expiresIn = result['expires_in']
        return True

    def loginByAccessToken(self, accessToken, userid=None):
        generation = self._sessionGeneration
        header = {'authorization': f'Bearer {accessToken}'}
        response = self.session.get('https://api.tidal.com/v1/sessions', headers=header, timeout=REQUEST_TIMEOUT)
        try:
            if response.status_code != 200:
                raise self.__httpError__('Login', response)
            result = response.json()
        except ValueError:
            raise Exception(f"Login failed: unexpected HTTP {response.status_code} response from TIDAL.")
        finally:
            response.close()
        if 'status' in result and result['status'] != 200:
            raise Exception("Login failed!")

        if not aigpy.string.isNull(userid):
            if str(result['userId']) != str(userid):
                raise Exception("User mismatch! Please use your own accesstoken.", )

        with self._authStateLock:
            if generation != self._sessionGeneration:
                raise TidalApiError('Login cancelled.')
            self.clearSessionCaches()
            self.key.userId = result['userId']
            self.key.countryCode = result['countryCode']
            self.key.accessToken = accessToken

        return

    def getAlbum(self, id) -> Album:
        return aigpy.model.dictToModel(self.__get__('albums/' + str(id)), Album())

    def getPlaylist(self, id) -> Playlist:
        return aigpy.model.dictToModel(self.__get__('playlists/' + str(id)), Playlist())

    def getArtist(self, id) -> Artist:
        return aigpy.model.dictToModel(self.__get__('artists/' + str(id)), Artist())

    def getTrack(self, id) -> Track:
        return aigpy.model.dictToModel(self.__get__('tracks/' + str(id)), Track())

    def getVideo(self, id) -> Video:
        return aigpy.model.dictToModel(self.__get__('videos/' + str(id)), Video())

    def getMix(self, id) -> Mix:
        mix = Mix()
        mix.id = id
        mix.tracks, mix.videos = self.getItems(id, Type.Mix)
        return mix

    def getTypeData(self, id, type: Type):
        if type == Type.Album:
            return self.getAlbum(id)
        if type == Type.Artist:
            return self.getArtist(id)
        if type == Type.Track:
            return self.getTrack(id)
        if type == Type.Video:
            return self.getVideo(id)
        if type == Type.Playlist:
            return self.getPlaylist(id)
        if type == Type.Mix:
            return self.getMix(id)
        return None

    def search(self, text: str, type: Type, offset: int = 0, limit: int = 10) -> SearchResult:
        typeStr = type.name.upper() + "S"

        if type == Type.Null:
            typeStr = "ARTISTS,ALBUMS,TRACKS,VIDEOS,PLAYLISTS"

        params = {"query": text,
                  "offset": offset,
                  "limit": limit,
                  "types": typeStr}
        return aigpy.model.dictToModel(self.__get__('search', params=params), SearchResult())

    def _asItemList(self, items):
        if items is None:
            return []
        if isinstance(items, list):
            return items
        return [items]

    def getSearchResultItems(self, result: SearchResult, type: Type):
        if result is None:
            return []
        bucket = SEARCH_BUCKETS.get(type)
        if not bucket:
            return []
        items = getattr(getattr(result, bucket, None), 'items', None)
        return self._asItemList(items)

    def __normalizeSearchName__(self, text) -> str:
        return re.sub(r'[^a-z0-9]+', '', (text or '').casefold())

    def findMatchingSearchArtists(self, text, artists=None):
        needle = self.__normalizeSearchName__(text)
        if len(needle) < 2:
            return []
        matches = []
        for artist in artists or []:
            name = self.__normalizeSearchName__(getattr(artist, 'name', None))
            if name and name == needle:
                matches.append(artist)
        return matches

    def searchAll(self, text: str, type: Type, offset: int = 0, limit: int = SEARCH_PAGE_SIZE,
                  max_items: int = SEARCH_MAX_ITEMS) -> SearchResult:
        """Page through catalog search instead of stopping at the first 10 hits."""
        kinds = list(SEARCH_RESULT_TYPES) if type == Type.Null else [type]
        merged = None
        page_offset = max(0, int(offset or 0))
        page_size = max(1, int(limit or SEARCH_PAGE_SIZE))
        cap = max(1, int(max_items or SEARCH_MAX_ITEMS))

        while page_offset < cap:
            page_limit = min(page_size, cap - page_offset)
            page = self.search(text, type, offset=page_offset, limit=page_limit)
            if page is None:
                return merged
            if merged is None:
                merged = page
                for kind in kinds:
                    bucket = getattr(merged, SEARCH_BUCKETS.get(kind, ''), None)
                    if bucket is not None:
                        bucket.items = self.getSearchResultItems(merged, kind)
            else:
                for kind in kinds:
                    bucket = getattr(merged, SEARCH_BUCKETS.get(kind, ''), None)
                    if bucket is None:
                        continue
                    bucket.items = self.getSearchResultItems(merged, kind) + self.getSearchResultItems(page, kind)

            more = False
            for kind in kinds:
                items = self.getSearchResultItems(page, kind)
                bucket = getattr(page, SEARCH_BUCKETS.get(kind, ''), None)
                total = int(getattr(bucket, 'totalNumberOfItems', 0) or 0)
                have = page_offset + len(items)
                page_cap = min(total, cap) if total else have
                if items and have < page_cap:
                    more = True
            if not more:
                break
            page_offset += page_limit
        return merged

    def mergeMatchingArtistAlbums(self, text, albums, artists=None, includeEP=True):
        """Prepend an artist's discography when the query is that artist's name.

        Album search ranks by title, so searching 'O.S.T.R.' hides albums such as
        'Masz to jak w Banku' and never returns some catalog variants.
        """
        matches = self.findMatchingSearchArtists(text, artists)
        existing = self._asItemList(albums)
        if not matches:
            return existing

        seen = set()
        merged = []

        def add(album):
            album_id = str(getattr(album, 'id', '') or '')
            if album_id and album_id in seen:
                return
            if album_id:
                seen.add(album_id)
            merged.append(album)

        for artist in matches:
            artist_id = getattr(artist, 'id', None)
            if artist_id is None or str(artist_id).strip() == '':
                continue
            try:
                discog = self.getArtistAlbums(artist_id, includeEP=includeEP) or []
            except DownloadCancelled:
                raise
            except Exception as e:
                logging.info("Unable to load albums for artist %s: %s", artist_id, e)
                continue
            for album in discog:
                add(album)
        for album in existing:
            add(album)
        return merged

    def searchAlbumsForQuery(self, text, includeEP=True):
        """Album search that also loads a matching artist's full album list."""
        artistResult = self.search(text, Type.Artist, offset=0, limit=SEARCH_PAGE_SIZE)
        artists = self.getSearchResultItems(artistResult, Type.Artist)
        if self.findMatchingSearchArtists(text, artists):
            result = self.search(text, Type.Album, offset=0, limit=SEARCH_PAGE_SIZE)
        else:
            result = self.searchAll(text, Type.Album)
        albums = self.mergeMatchingArtistAlbums(
            text,
            self.getSearchResultItems(result, Type.Album),
            artists,
            includeEP=includeEP,
        )
        return self.preferAtmosSearchAlbums(albums)

    def getLyrics(self, id) -> Lyrics:
        data = self.__get__(f'tracks/{str(id)}/lyrics', urlpre='https://api.tidal.com/v1/')
        return aigpy.model.dictToModel(data, Lyrics())

    def getItems(self, id, type: Type):
        if type == Type.Playlist:
            data = self.__getItems__('playlists/' + str(id) + "/items")
        elif type == Type.Album:
            data = self.__getItems__('albums/' + str(id) + "/items")
        elif type == Type.Mix:
            data = self.__getItems__('mixes/' + str(id) + '/items')
        else:
            raise Exception("invalid Type!")

        tracks = []
        videos = []
        for item in data:
            itemType = item.get('type')
            payload = item.get('item') or {}
            if itemType == 'track':
                if payload.get('streamReady', True):
                    tracks.append(aigpy.model.dictToModel(payload, Track()))
                else:
                    report_warning(f"Skipped unavailable track: {payload.get('title', payload.get('id', 'unknown'))}")
            elif itemType == 'video':
                videos.append(aigpy.model.dictToModel(payload, Video()))
        return tracks, videos

    def getArtistAlbums(self, id, includeEP=False):
        cache = self._artistAlbumsCache
        cache_key = (str(id), bool(includeEP))
        if cache_key in cache:
            return list(cache[cache_key])

        data = self.__getItems__(f'artists/{str(id)}/albums')
        albums = list(aigpy.model.dictToModel(item, Album()) for item in data)
        if includeEP:
            data = self.__getItems__(f'artists/{str(id)}/albums', {"filter": "EPSANDSINGLES"})
            albums += list(aigpy.model.dictToModel(item, Album()) for item in data)
        cache[cache_key] = list(albums)
        return albums

    def preferAtmosSearchAlbums(self, albums):
        """Insert Atmos catalog twins for stereo album search hits when missing.

        TIDAL album search often omits Dolby Atmos releases even when a stereo
        LOSSLESS row for the same title is present.
        """
        if not albums:
            return []

        seen = set()
        enriched = []
        for album in albums:
            album_id = str(getattr(album, "id", "") or "")
            if album_id and album_id in seen:
                continue
            if album_id:
                seen.add(album_id)
            enriched.append(album)

            if self.__hasAtmosMode__(album):
                continue
            twin = self.findAtmosAlbumVariant(album)
            twin_id = str(getattr(twin, "id", "") or "") if twin is not None else ""
            if not twin_id or twin_id in seen or twin_id == album_id:
                continue
            seen.add(twin_id)
            enriched.append(twin)
        return enriched

    def getArtistVideos(self, id):
        data = self.__getItems__(f'artists/{str(id)}/videos')
        videos = []
        for item in data:
            if isinstance(item, dict) and item.get('type') == 'video' and 'item' in item:
                item = item['item']
            videos.append(aigpy.model.dictToModel(item, Video()))
        return videos

    # from https://github.com/Dniel97/orpheusdl-tidal/blob/master/interface.py#L582
    def parse_mpd(self, xml) -> list:
        try:
            return dash_segments(xml)
        except ProtectedManifestError as error:
            # Let configured quality fallbacks use an available clear stream;
            # never return encrypted DASH bytes as playable audio.
            raise TidalStreamUnavailable(str(error)) from error

    def __decodeManifestDataUri__(self, uri):
        if not isinstance(uri, str) or ',' not in uri:
            raise TidalStreamUnavailable('Stream manifest is empty.')
        header, payload = uri.split(',', 1)
        if ';base64' not in header.lower():
            raise TidalStreamUnavailable('Stream manifest encoding is unsupported.')
        try:
            return base64.b64decode(payload, validate=True).decode('utf-8')
        except (ValueError, UnicodeDecodeError) as error:
            raise TidalStreamUnavailable('Stream manifest is invalid.') from error

    def __dashStreamUrl__(self, track_id, sound_quality, xmldata, **facts):
        try:
            representation = best_dash_representation(xmldata)
        except ProtectedManifestError as error:
            raise TidalStreamUnavailable(str(error)) from error
        ret = StreamUrl()
        ret.trackid = track_id
        ret.soundQuality = sound_quality
        ret.manifestMimeType = 'application/dash+xml'
        ret.codec = representation.get('codec') or aigpy.string.getSub(xmldata, 'codecs="', '"')
        ret.encryptionKey = ''
        ret.urls = representation['urls']
        media_type = representation.get('mimeType') or ''
        ret.container = 'mp4' if not media_type or 'mp4' in media_type.lower() else media_type
        ret.bitDepth = representation.get('bitDepth') or facts.get('bitDepth')
        ret.sampleRate = representation.get('sampleRate') or facts.get('sampleRate')
        ret.bandwidth = representation.get('bandwidth')
        ret.channels = representation.get('channels')
        ret.representationId = representation.get('id')
        ret.manifestHash = facts.get('manifestHash')
        if ret.urls:
            ret.url = ret.urls[0]
        return ret

    def __openApiFormatsForQuality__(self, quality: AudioQuality):
        if quality in (AudioQuality.Max, AudioQuality.Master):
            return ['FLAC_HIRES', 'FLAC']
        return ['FLAC']

    def __openApiManifestUsages__(self):
        return ('DOWNLOAD', 'PLAYBACK')

    def __isRetryableManifestError__(self, error):
        if not isinstance(error, TidalApiError):
            return False
        if self.__isStaleClientError__(error):
            # Retry a different configured quality, not every usage/format
            # permutation of a client the manifest service just rejected.
            return False
        # Permanent entitlement blocks are not fixed by switching DOWNLOAD↔PLAYBACK.
        # Retrying doubles rate-limited OpenAPI traffic for no gain (e.g. Atmos on stereo).
        if 'CLIENT_NOT_ENTITLED' in error.errorCodes:
            return False
        if 'PREREQUISITE_MISSING' in error.errorCodes:
            return True
        # Other 403/404/405 can still be usage- or format-specific.
        return error.statusCode in (403, 404, 405)

    def __getOpenApiTrackManifest__(self, id, formats, usages=None):
        formats = list(formats)
        formatAttempts = [formats]
        if len(formats) > 1:
            # HTTP 403 PREREQUISITE_MISSING can be triggered by the hi-res
            # format alone; retry with only the base format before giving up.
            formatAttempts.append(formats[-1:])

        last_error = None
        for usage in usages or self.__openApiManifestUsages__():
            for attemptFormats in formatAttempts:
                try:
                    attributes = self.__getOpenApiTrackManifestOnce__(id, attemptFormats, usage)
                except TidalApiError as e:
                    last_error = e
                    if not self.__isRetryableManifestError__(e):
                        raise
                    logging.debug(
                        "Track manifest usage=%s formats=%s unavailable, trying next option: %s",
                        usage,
                        attemptFormats,
                        e,
                    )
                    continue

                presentation = str(attributes.get('trackPresentation') or 'FULL').strip().upper()
                if presentation == 'PREVIEW':
                    # DOWNLOAD can return a valid, full-fidelity manifest that
                    # contains only a short preview. Codec/sample-rate checks
                    # cannot detect that truncation, so retry the same formats
                    # with PLAYBACK and never report a preview as completed.
                    last_error = TidalStreamUnavailable(
                        'TIDAL returned a preview-only stream instead of the full track.'
                    )
                    logging.debug(
                        "Track manifest usage=%s formats=%s returned PREVIEW; trying next usage.",
                        usage,
                        attemptFormats,
                    )
                    break
                return attributes
        raise last_error

    def __getOpenApiTrackManifestOnce__(self, id, formats, usage):
        params = [
            ('manifestType', 'MPEG_DASH'),
            ('uriScheme', 'DATA'),
            ('usage', usage),
            ('adaptive', 'false'),
        ]
        for item in formats:
            params.append(('formats', item))

        response = None
        try:
            refreshedToken = False
            rateLimitBudget = RateLimitWaitBudget()
            # Mirrors __getOnce__: only asset-not-ready responses consume attempts;
            # 429s are bounded by the wait budget and token refresh happens once.
            attempt = 0
            while attempt < PLAYBACK_ASSET_NOT_READY_ATTEMPTS:
                check_cancelled()
                self.__waitForStreamRequestQuota__()
                response = self.session.get(
                    f'https://openapi.tidal.com/v2/trackManifests/{str(id)}',
                    headers={
                        'authorization': f'Bearer {self.key.accessToken}',
                        'Accept': 'application/vnd.api+json',
                    },
                    params=params,
                    timeout=REQUEST_TIMEOUT,
                )

                if response.status_code == 429:
                    self.__backOffForRateLimit__("Track manifest request", response, rateLimitBudget)
                    continue

                if response.status_code == 401 and self.__isAssetNotReady__(response):
                    self.__backOffForAssetNotReady__(response, attempt)
                    attempt += 1
                    continue

                if response.status_code == 401 and not refreshedToken and self.__refreshSavedAccessToken__():
                    refreshedToken = True
                    response.close()
                    continue

                break

            if self.__isStaleClientResponse__(response):
                raise self.__playbackClientError__(
                    f'openapi/v2/trackManifests/{id}', f'{",".join(formats)} ({usage})',
                )
            if response is None or response.status_code != 200:
                raise self.__httpError__("Track manifest request", response)

            try:
                data = response.json()
            except ValueError as error:
                raise TidalApiError(
                    "Track manifest request failed: TIDAL returned invalid JSON.",
                    response.status_code,
                ) from error
            if not isinstance(data, dict):
                raise TidalApiError(
                    "Track manifest request failed: TIDAL returned an invalid JSON payload.",
                    response.status_code,
                )
            attributes = data.get('data', {}).get('attributes')
            if not isinstance(attributes, dict):
                raise TidalApiError(
                    "Track manifest request failed: response attributes are missing.",
                    response.status_code,
                )
            self.__rewardStreamRequest__()
            return attributes
        finally:
            if response is not None:
                response.close()

    def __openApiFlacSoundQuality__(self, formats):
        available = set(formats or [])
        if 'FLAC_HIRES' in available:
            return 'HI_RES_LOSSLESS'
        if 'FLAC' in available:
            return 'LOSSLESS'
        return None

    def __getAtmosStreamUrl__(self, id):
        track_id = str(id)
        if track_id in self._atmosUnavailableTrackIds:
            raise TidalStreamUnavailable("Dolby Atmos stream is not available for this track.")

        try:
            attrs = self.__getOpenApiTrackManifest__(id, ['EAC3_JOC'])
        except DownloadCancelled:
            raise
        except Exception as e:
            if self.__isPermanentAtmosUnavailableError__(e):
                self._atmosUnavailableTrackIds.add(track_id)
            raise

        formats = attrs.get('formats') or []
        if 'EAC3_JOC' not in formats:
            self._atmosUnavailableTrackIds.add(track_id)
            raise TidalStreamUnavailable("Dolby Atmos stream is not available for this track.")

        uri = attrs.get('uri') or ''
        if ',' not in uri:
            self._atmosUnavailableTrackIds.add(track_id)
            raise TidalStreamUnavailable("Dolby Atmos manifest is empty.")

        xmldata = self.__decodeManifestDataUri__(uri)
        ret = self.__dashStreamUrl__(id, 'DOLBY_ATMOS', xmldata, manifestHash=attrs.get('manifestHash'))
        self._atmosUnavailableTrackIds.discard(track_id)
        return ret

    def __isPermanentAtmosUnavailableError__(self, error):
        if isinstance(error, TidalStreamUnavailable):
            return True
        if not isinstance(error, TidalApiError):
            return False
        # Only cache catalog/entitlement misses. Generic 403/404 can be
        # transient CDN/auth glitches that Retry Failed should try again.
        return 'CLIENT_NOT_ENTITLED' in error.errorCodes

    def __getOpenApiFlacStreamUrl__(self, id, quality: AudioQuality):
        requested_formats = self.__openApiFormatsForQuality__(quality)
        attrs = self.__getOpenApiTrackManifest__(id, requested_formats)
        formats = attrs.get('formats') or []
        sound_quality = self.__openApiFlacSoundQuality__(formats)
        if sound_quality is None:
            raise TidalStreamUnavailable("Lossless FLAC stream is not available for this track.")

        uri = attrs.get('uri') or ''
        if ',' not in uri:
            raise TidalStreamUnavailable("Lossless FLAC manifest is empty.")

        xmldata = self.__decodeManifestDataUri__(uri)
        return self.__dashStreamUrl__(id, sound_quality, xmldata, manifestHash=attrs.get('manifestHash'))

    def __getAudioStreamUrlForQuality__(self, id, quality: AudioQuality):
        chain = []
        if quality == AudioQuality.Atmos:
            # Atmos is OpenAPI-only. Do not probe standard playback with the
            # accidental HI_RES mapping — that wastes a limited call and is not
            # the next quality the user configured (use quality-priority instead).
            chain.append(lambda: self.__getAtmosStreamUrl__(id))
        else:
            if quality in (AudioQuality.HiFi, AudioQuality.Max, AudioQuality.Master):
                chain.append(lambda q=quality: self.__getOpenApiFlacStreamUrl__(id, q))
            chain.append(lambda: self.__getStandardStreamUrl__(id, quality))

        last_error = None
        last_stream = None
        for index, getter in enumerate(chain):
            try:
                stream = getter()
                mismatch = self.__streamQualityMismatch__(stream, quality)
                if mismatch is not None and index < len(chain) - 1:
                    last_error = mismatch
                    last_stream = stream
                    continue
                return stream
            except DownloadCancelled:
                raise
            except Exception as e:
                last_error = e
                if index < len(chain) - 1 and self.__shouldSkipOpenApiFallback__(e):
                    break
        if last_stream is not None:
            return last_stream
        raise last_error

    def __audioQualityParam__(self, quality: AudioQuality):
        if quality == AudioQuality.Normal:
            return "LOW"
        if quality == AudioQuality.High:
            return "HIGH"
        if quality == AudioQuality.HiFi:
            return "LOSSLESS"
        if quality in (AudioQuality.Max, AudioQuality.Master):
            return "HI_RES_LOSSLESS"
        return "HI_RES"

    def __audioQualityLabel__(self, quality: AudioQuality):
        labels = {
            AudioQuality.Atmos: 'Dolby Atmos',
            AudioQuality.Max: 'Max',
            AudioQuality.Master: 'Master',
            AudioQuality.HiFi: 'HiFi',
            AudioQuality.High: 'High',
            AudioQuality.Normal: 'Normal',
        }
        return labels.get(quality, str(quality))

    def __streamAudioQuality__(self, stream):
        quality = (getattr(stream, 'soundQuality', None) or '').upper()
        labels = {
            'DOLBY_ATMOS': AudioQuality.Atmos,
            'HI_RES_LOSSLESS': AudioQuality.Max,
            'HI_RES': AudioQuality.Master,
            'LOSSLESS': AudioQuality.HiFi,
            'HIGH': AudioQuality.High,
            'LOW': AudioQuality.Normal,
        }
        return labels.get(quality)

    def __streamQualityMismatch__(self, stream, requestedQuality):
        actualQuality = self.__streamAudioQuality__(stream)
        if actualQuality == requestedQuality:
            return None

        actualLabel = getattr(stream, 'soundQuality', None) or 'unknown'
        return TidalStreamUnavailable(
            f"Requested {self.__audioQualityLabel__(requestedQuality)} but TIDAL returned {actualLabel}."
        )

    def __fallbackReason__(self, error):
        if isinstance(error, TidalPlaybackClientError):
            return "playback client rejected the requested format"
        if isinstance(error, TidalStreamUnavailable):
            return "requested format is unavailable"
        if isinstance(error, TidalApiError):
            if 'CLIENT_NOT_ENTITLED' in error.errorCodes:
                return "requested format is not allowed for this account or track"
            if 'PREREQUISITE_MISSING' in error.errorCodes:
                return "requested format prerequisites are missing for this account"
            if error.statusCode == 403:
                return "requested format was blocked"
        return "requested format failed"

    def __annotateStreamFallback__(self, stream, requestedQuality, actualQuality, fallbackError):
        stream.requestedQuality = self.__audioQualityLabel__(requestedQuality)
        if fallbackError is None:
            return stream

        stream.fallbackQuality = self.__audioQualityLabel__(actualQuality)
        stream.fallbackReason = self.__fallbackReason__(fallbackError)
        stream.fallbackError = str(fallbackError)
        return stream

    def __isStreamFallbackError__(self, error):
        if isinstance(error, TidalStreamUnavailable):
            return True
        if isinstance(error, TidalApiError):
            if 'CLIENT_NOT_ENTITLED' in error.errorCodes:
                return True
            return error.statusCode == 403
        message = str(error)
        return "CLIENT_NOT_ENTITLED" in message or "HTTP 403" in message

    def __isManifestFallbackError__(self, error):
        if isinstance(error, TidalPlaybackClientError):
            return True
        if self.__isRateLimitError__(error) or self.__isStaleClientError__(error):
            return False
        if self.__isStreamFallbackError__(error):
            return True
        text = str(error or "").lower()
        return any(token in text for token in (
            "get operation err",
            "not ready for playback",
            "asset is not ready",
            "can't get the streamurl",
        ))

    def __normalizeAudioQuality__(self, quality):
        if isinstance(quality, AudioQuality):
            return quality
        return Settings().getAudioQualityOrNone(quality)

    def __getStandardStreamUrl__(self, id, quality: AudioQuality):
        audio_param = self.__audioQualityParam__(quality)
        if self.__isPlaybackParamBlocked__(audio_param):
            raise TidalStreamUnavailable(
                f"Playback API is unavailable for {audio_param}; using OpenAPI manifest."
            )

        paras = {
            "audioquality": audio_param,
            "playbackmode": "STREAM",
            "assetpresentation": "FULL",
        }
        try:
            data = self.__getPlaybackData__(id, paras)
        except DownloadCancelled:
            raise
        except Exception as e:
            self.__markPlaybackParamBlocked__(audio_param, e)
            raise
        resp = aigpy.model.dictToModel(data, StreamRespond())

        if "vnd.tidal.bt" in resp.manifestMimeType:
            manifest = json.loads(base64.b64decode(resp.manifest).decode('utf-8'))
            ret = StreamUrl()
            ret.trackid = resp.trackid
            ret.soundQuality = resp.audioQuality
            ret.manifestMimeType = resp.manifestMimeType
            ret.codec = manifest['codecs']
            ret.encryptionKey = manifest['keyId'] if 'keyId' in manifest else ""
            ret.url = manifest['urls'][0]
            ret.urls = [ret.url]
            ret.container = manifest.get('mimeType', '')
            ret.bitDepth = resp.bitDepth or manifest.get('bitDepth')
            ret.sampleRate = resp.sampleRate or manifest.get('sampleRate')
            return ret
        elif "dash+xml" in resp.manifestMimeType:
            xmldata = base64.b64decode(resp.manifest).decode('utf-8')
            return self.__dashStreamUrl__(
                resp.trackid,
                resp.audioQuality,
                xmldata,
                bitDepth=resp.bitDepth,
                sampleRate=resp.sampleRate,
            )

        raise Exception("Can't get the streamUrl, type is " + resp.manifestMimeType)

    def __streamCacheKey__(self, id, qualities):
        return (self._sessionGeneration, self.key.userId, self.key.countryCode,
                self.apiKey.get('clientId'), str(id), tuple(quality.name for quality in qualities))

    def __getCachedStream__(self, key):
        now = time.monotonic()
        with self._streamCacheLock:
            cached = self._streamCache.get(key)
            if cached is None:
                return None
            created, stream = cached
            if now - created > STREAM_CACHE_TTL_SECONDS:
                self._streamCache.pop(key, None)
                return None
            self._streamCache.move_to_end(key)
            return copy.deepcopy(stream)

    def __cacheStream__(self, key, stream):
        now = time.monotonic()
        with self._streamCacheLock:
            # OrderedDict keeps insertion/access order, allowing expired and LRU
            # entries to be removed in O(1) instead of scanning the full cache.
            while self._streamCache:
                oldestKey = next(iter(self._streamCache))
                created, _ = self._streamCache[oldestKey]
                if now - created <= STREAM_CACHE_TTL_SECONDS:
                    break
                self._streamCache.popitem(last=False)
            self._streamCache.pop(key, None)
            while len(self._streamCache) >= STREAM_CACHE_MAX_ITEMS:
                self._streamCache.popitem(last=False)
            self._streamCache[key] = (now, copy.deepcopy(stream))

    def getStreamUrlByPriority(self, id, qualities):
        priority = []
        for quality in qualities or []:
            normalized = self.__normalizeAudioQuality__(quality)
            if normalized is not None and normalized not in priority:
                priority.append(normalized)
        if not priority:
            priority = [AudioQuality.Normal]

        # Keep the original request in the cache key and download diagnostics.
        # TIDAL retired MQA in July 2024. Legacy Master profiles should request
        # its FLAC replacement, not HI_RES or an impossible exact MQA match.
        cacheKey = self.__streamCacheKey__(id, priority)
        requestedQuality = priority[0]
        priority = playback_quality_priority(priority)
        cached = self.__getCachedStream__(cacheKey)
        if cached is not None:
            return cached

        # One stream resolve at a time across multi-thread downloads.
        with self._streamResolveLock:
            cached = self.__getCachedStream__(cacheKey)
            if cached is not None:
                return cached

            lastError = None
            if requestedQuality == AudioQuality.Master:
                lastError = TidalStreamUnavailable("Master (MQA) was retired by TIDAL; using lossless FLAC.")
            for index, item in enumerate(priority):
                try:
                    stream = self.__getAudioStreamUrlForQuality__(id, item)
                    mismatch = self.__streamQualityMismatch__(stream, item)
                    if mismatch is not None:
                        lastError = mismatch
                        if index == len(priority) - 1:
                            raise mismatch
                        continue
                    stream = self.__annotateStreamFallback__(stream, requestedQuality, item, lastError)
                    self.__cacheStream__(cacheKey, stream)
                    return stream
                except DownloadCancelled:
                    raise
                except Exception as e:
                    lastError = e
                    if index == len(priority) - 1 or not self.__isManifestFallbackError__(e):
                        raise
            raise lastError

    def getStreamUrl(self, id, quality: AudioQuality):
        # Share stream-manifest cache with the priority path used by downloads.
        return self.getStreamUrlByPriority(id, audio_quality_fallbacks(quality))

    def getVideoStreamUrl(self, id, quality: VideoQuality):
        paras = {"videoquality": "HIGH", "playbackmode": "STREAM", "assetpresentation": "FULL"}
        data = self.__getPlaybackData__(id, paras, media='videos')
        resp = aigpy.model.dictToModel(data, StreamRespond())

        if "vnd.tidal.emu" in resp.manifestMimeType:
            manifest = json.loads(base64.b64decode(resp.manifest).decode('utf-8'))
            array = self.__getResolutionList__(manifest['urls'][0])
            icmp = int(quality.value)
            index = 0
            for item in array:
                if icmp <= int(item.resolutions[1]):
                    break
                index += 1
            if index >= len(array):
                index = len(array) - 1
            return array[index]
        raise Exception("Can't get the streamUrl, type is " + resp.manifestMimeType)

    def getTrackContributors(self, id):
        return self.__get__(f'tracks/{str(id)}/contributors')

    def getCoverUrl(self, sid, width="320", height="320"):
        if sid is None:
            return ""
        return f"https://resources.tidal.com/images/{sid.replace('-', '/')}/{width}x{height}.jpg"

    def __artistList__(self, artists):
        if isinstance(artists, (list, tuple)):
            return [item for item in artists if item is not None]
        return []

    def getArtistsID(self, artists=None):
        return ", ".join(
            str(getattr(item, 'id', None))
            for item in self.__artistList__(artists)
            if getattr(item, 'id', None) is not None
        )

    def getArtistsName(self, artists=None):
        return ", ".join(
            getattr(item, 'name', None)
            for item in self.__artistList__(artists)
            if getattr(item, 'name', None)
        )

    def __hasAtmosMode__(self, data) -> bool:
        modes = getattr(data, "audioModes", None) or []
        return any(str(mode).upper() == "DOLBY_ATMOS" for mode in modes)

    def getFlag(self, data, type: Type, short=True, separator=" / "):
        master = False
        atmos = False
        explicit = False
        if type == Type.Album or type == Type.Track:
            if data.audioQuality == "HI_RES":
                master = True
            # Atmos catalog rows often report audioQuality=LOW; audioModes is the real signal.
            if self.__hasAtmosMode__(data):
                atmos = True
            if data.explicit is True:
                explicit = True
        if type == Type.Video:
            if data.explicit is True:
                explicit = True
        if not master and not atmos and not explicit:
            return ""
        array = []
        if master:
            array.append("M" if short else "Master")
        if atmos:
            array.append("A" if short else "Dolby Atmos")
        if explicit:
            array.append("E" if short else "Explicit")
        return separator.join(array)

    def __normalizeCatalogTitle__(self, title) -> str:
        text = (title or "").strip().lower()
        return " ".join(text.split())

    def findAtmosAlbumVariant(self, album: Album):
        """Return a Dolby Atmos catalog twin for a stereo album, or the album itself.

        TIDAL keeps Atmos mixes as separate album/track IDs. Search often ranks the
        stereo LOSSLESS release first; the Atmos release usually has audioQuality=LOW
        and audioModes containing DOLBY_ATMOS.
        """
        if album is None:
            return None
        if self.__hasAtmosMode__(album):
            return album

        album_id = str(getattr(album, "id", "") or "")
        if album_id and album_id in self._atmosAlbumTwinCache:
            cached = self._atmosAlbumTwinCache[album_id]
            return album if cached is None else cached

        artist_id = None
        artist = getattr(album, "artist", None)
        if artist is not None and getattr(artist, "id", None) is not None:
            artist_id = artist.id
        if artist_id is None:
            for item in self.__artistList__(getattr(album, "artists", None)):
                if getattr(item, "id", None) is not None:
                    artist_id = item.id
                    break
        if artist_id is None:
            if album_id:
                self._atmosAlbumTwinCache[album_id] = None
            return None

        target_title = self.__normalizeCatalogTitle__(getattr(album, "title", None))
        if not target_title:
            if album_id:
                self._atmosAlbumTwinCache[album_id] = None
            return None

        try:
            candidates = self.getArtistAlbums(artist_id, includeEP=True) or []
        except DownloadCancelled:
            raise
        except Exception as e:
            logging.info("Unable to look up Atmos album variant for album %s: %s", getattr(album, "id", ""), e)
            return None

        matches = []
        for candidate in candidates:
            if not self.__hasAtmosMode__(candidate):
                continue
            if self.__normalizeCatalogTitle__(getattr(candidate, "title", None)) != target_title:
                continue
            matches.append(candidate)
        if not matches:
            if album_id:
                self._atmosAlbumTwinCache[album_id] = None
            return None

        def score(candidate):
            track_delta = abs(
                int(getattr(candidate, "numberOfTracks", 0) or 0)
                - int(getattr(album, "numberOfTracks", 0) or 0)
            )
            same_explicit = int(bool(getattr(candidate, "explicit", False)) != bool(getattr(album, "explicit", False)))
            return (track_delta, same_explicit, str(getattr(candidate, "id", "")))

        best = sorted(matches, key=score)[0]
        if str(getattr(best, "id", "")) == str(getattr(album, "id", "")):
            if album_id:
                self._atmosAlbumTwinCache[album_id] = None
            return album
        if album_id:
            self._atmosAlbumTwinCache[album_id] = best
        return best

    def findAtmosTrackVariant(self, track: Track):
        """Return a Dolby Atmos catalog twin for a stereo track when available."""
        if track is None:
            return None
        if self.__hasAtmosMode__(track):
            return track

        track_id = str(getattr(track, "id", "") or "")
        if track_id and track_id in self._atmosTrackTwinCache:
            return self._atmosTrackTwinCache[track_id]

        album_ref = getattr(track, "album", None)
        album_id = getattr(album_ref, "id", None) if album_ref is not None else None
        if album_id is None:
            if track_id:
                self._atmosTrackTwinCache[track_id] = None
            return None

        try:
            album = self.getAlbum(album_id)
        except DownloadCancelled:
            raise
        except Exception as e:
            logging.info("Unable to load album %s for Atmos track variant: %s", album_id, e)
            return None

        atmos_album = self.findAtmosAlbumVariant(album)
        if atmos_album is None or str(getattr(atmos_album, "id", "")) == str(album_id):
            if track_id:
                self._atmosTrackTwinCache[track_id] = None
            return None

        try:
            atmos_tracks, _ = self.getItems(atmos_album.id, Type.Album)
        except DownloadCancelled:
            raise
        except Exception as e:
            logging.info("Unable to list Atmos album %s tracks: %s", getattr(atmos_album, "id", ""), e)
            return None

        target_title = self.__normalizeCatalogTitle__(getattr(track, "title", None))
        target_isrc = (getattr(track, "isrc", None) or "").strip().upper()
        target_number = getattr(track, "trackNumber", None)
        target_volume = getattr(track, "volumeNumber", None)

        matched = None
        for candidate in atmos_tracks or []:
            if target_isrc and (getattr(candidate, "isrc", None) or "").strip().upper() == target_isrc:
                matched = candidate
                break
        if matched is None:
            for candidate in atmos_tracks or []:
                if target_number is not None and getattr(candidate, "trackNumber", None) == target_number:
                    if target_volume is None or getattr(candidate, "volumeNumber", None) == target_volume:
                        if self.__normalizeCatalogTitle__(getattr(candidate, "title", None)) == target_title:
                            matched = candidate
                            break
        if matched is None:
            for candidate in atmos_tracks or []:
                if self.__normalizeCatalogTitle__(getattr(candidate, "title", None)) == target_title:
                    matched = candidate
                    break

        if track_id:
            self._atmosTrackTwinCache[track_id] = matched
        return matched

    def parseUrl(self, url):
        if "tidal.com" not in url:
            return Type.Null, url

        parsed = urlparse(url)
        path_parts = [unquote(part) for part in parsed.path.split('/') if part]
        lowered = [part.lower() for part in path_parts]
        type_by_name = {item.name.lower(): item for item in Type if item != Type.Null}
        for index in range(len(lowered) - 2, -1, -1):
            item = type_by_name.get(lowered[index])
            if item is not None:
                return item, path_parts[index + 1]
        return Type.Null, url

    def __isProbeableLookupError__(self, error):
        """True when type probing should try the next media type."""
        if self.__isRateLimitError__(error) or self.__isStaleClientError__(error):
            return False
        if isinstance(error, TidalApiError):
            # Auth / entitlement / client errors must not look like "not found".
            if error.statusCode in (401, 403):
                return False
            if error.statusCode in (400, 404, 405, 406, 410, 422):
                return True
            # Unexpected server / transport-ish API failures should surface.
            return False
        if isinstance(error, (requests.RequestException, OSError, TimeoutError)):
            return False
        text = str(error or "").lower()
        # Common not-found / wrong-type probe noise.
        if any(token in text for token in ("not found", "no result", "resource not found")):
            return True
        if "404" in text:
            return True
        return False

    def getByString(self, string):
        if aigpy.string.isNull(string):
            raise Exception("Please enter something.")

        etype, sid = self.parseUrl(string)
        lastError = None
        for index, item in enumerate(Type):
            if etype != Type.Null and etype != item:
                continue
            if item == Type.Null:
                continue
            try:
                obj = self.getTypeData(sid, item)
                return item, obj
            except DownloadCancelled:
                raise
            except Exception as e:
                lastError = e
                # Surface auth, entitlement, throttling, and network problems
                # instead of masking them as a generic "No result." while probing.
                if not self.__isProbeableLookupError__(e):
                    raise
                continue

        if lastError is not None and not self.__isProbeableLookupError__(lastError):
            raise lastError
        raise Exception("No result.")

# Singleton
TIDAL_API = TidalAPI()
