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
import random
import re
import time
import base64
import json
import logging
from threading import Lock
from typing import List
from xml.etree import ElementTree
from urllib.parse import unquote, urlparse

import requests

from .model import *
from .settings import *

# Retry number
requests.adapters.DEFAULT_RETRIES = 5
REQUEST_TIMEOUT = (5, 60)
API_BASE_PRIMARY = 'https://api.tidal.com/v1/'
API_BASE_LEGACY = 'https://api.tidalhifi.com/v1/'
PLAYBACK_ASSET_NOT_READY_ATTEMPTS = 6
RATE_LIMIT_MAX_ATTEMPTS = 3


class RequestRateLimiter:
    def __init__(self, minInterval=1.0, jitter=0.5):
        self.minInterval = minInterval
        self.jitter = jitter
        self._lock = Lock()
        self._nextAllowed = 0.0

    def wait(self):
        if self.minInterval <= 0:
            return 0.0

        with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._nextAllowed - now)
            base = now + delay
            self._nextAllowed = base + self.minInterval + random.uniform(0, self.jitter)

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
        adapter = requests.adapters.HTTPAdapter(pool_connections=8, pool_maxsize=16)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.playbackRateLimiter = PLAYBACK_RATE_LIMITER
        self._playbackBlockedParams = set()

    def __responseBody__(self, response):
        try:
            return response.json()
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
        if self.__isPlaybackPath__(path):
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

    def __httpError__(self, action, response):
        detail = response.text[:200].replace("\n", " ")
        return TidalApiError(
            f"{action} failed: HTTP {response.status_code} {detail}",
            response.status_code,
            self.__responseErrorCodes__(response),
        )

    def __refreshSavedAccessToken__(self):
        if aigpy.string.isNull(getattr(TOKEN, 'refreshToken', None)):
            return False

        try:
            if not self.refreshAccessToken(TOKEN.refreshToken):
                return False

            TOKEN.userid = self.key.userId
            TOKEN.countryCode = self.key.countryCode
            TOKEN.accessToken = self.key.accessToken
            TOKEN.refreshToken = self.key.refreshToken
            TOKEN.expiresAfter = time.time() + int(self.key.expiresIn)
            TOKEN.save()
            return True
        except Exception as e:
            logging.info("Unable to refresh saved access token: %s", e)
            return False

    def __requestIntervalSeconds__(self):
        if SETTINGS.downloadDelay is False:
            return 0.0
        return max(0.0, float(getattr(SETTINGS, 'requestIntervalSeconds', 1.0) or 0.0))

    def __waitForStreamRequestQuota__(self, *, light=False):
        if SETTINGS.downloadDelay is False:
            return
        syncPlaybackRateLimiter()
        if light:
            interval = self.playbackRateLimiter.minInterval
            try:
                self.playbackRateLimiter.minInterval = min(1.0, interval)
                self.playbackRateLimiter.wait()
            finally:
                self.playbackRateLimiter.minInterval = interval
            return
        self.playbackRateLimiter.wait()

    def __isPlaybackBlockedError__(self, error):
        if not isinstance(error, TidalApiError):
            return False
        if error.statusCode in (403, 404, 405):
            return True
        if 'CLIENT_NOT_ENTITLED' in error.errorCodes:
            return True
        return False

    def __isNonRetryableTidalApiError__(self, error, playbackRequest=False):
        if not isinstance(error, TidalApiError):
            return False
        if error.statusCode == 429:
            return False
        if self.__isPlaybackBlockedError__(error):
            return True
        if playbackRequest and error.statusCode == 401:
            return True
        return error.statusCode in (400, 404, 405, 406, 410, 422)

    def __isStaleClientError__(self, error):
        if isinstance(error, TidalApiError) and any(str(code) == '4022' for code in error.errorCodes):
            return True
        text = str(error or "").lower()
        return 'client referenced in the request' in text or 'substatus 4022' in text

    def __isStaleClientResponse__(self, response):
        if response is None or response.status_code != 404:
            return False
        body = self.__responseBody__(response)
        if str(body.get('subStatus', body.get('sub_status', ''))) == '4022':
            return True
        return 'client referenced in the request' in str(body.get('userMessage', '')).lower()

    def __markPlaybackParamBlocked__(self, audio_param, error):
        if not audio_param or not isinstance(error, TidalApiError):
            return
        if self.__isStaleClientError__(error):
            # A stale login session is an auth problem, not a capability block.
            return
        # Only cache client-level capability blocks. A track-specific 403
        # (for example PREREQUISITE_MISSING) must not disable the playback
        # API for every other track in this session.
        if 'CLIENT_NOT_ENTITLED' in error.errorCodes or error.statusCode in (404, 405):
            self._playbackBlockedParams.add(audio_param)

    def __isRateLimitError__(self, error):
        if isinstance(error, TidalApiError) and error.statusCode == 429:
            return True
        text = str(error or "").lower()
        return any(token in text for token in ("429", "too many requests", "rate limit"))

    def __shouldSkipOpenApiFallback__(self, error):
        return self.__isRateLimitError__(error) or self.__isStaleClientError__(error)

    def __retryAfter__(self, response, attempt):
        retryAfter = getattr(response, 'headers', {}).get('Retry-After') if response is not None else None
        delay = None
        if retryAfter:
            try:
                delay = min(float(retryAfter), 300)
            except ValueError:
                pass
        if delay is None:
            delay = min(5 * (attempt + 1), 30)
        minimum = self.__requestIntervalSeconds__()
        if minimum > 0:
            delay = max(delay, minimum)
        return delay

    def __get__(self, path, params=None, urlpre=None):
        if urlpre is not None:
            return self.__getOnce__(path, params, urlpre)
        try:
            return self.__getOnce__(path, params, API_BASE_PRIMARY)
        except Exception as e:
            if self.__shouldTryLegacyApiHost__(path, e):
                return self.__getOnce__(path, params, API_BASE_LEGACY)
            raise

    def __getOnce__(self, path, params=None, urlpre=API_BASE_PRIMARY):
        params = {} if params is None else dict(params)
        params['countryCode'] = self.key.countryCode
        errmsg = "Get operation err!"
        respond = None
        refreshedToken = False
        url = urlpre + path
        playbackRequest = self.__isPlaybackPath__(path)
        maxAttempts = PLAYBACK_ASSET_NOT_READY_ATTEMPTS if playbackRequest else 3
        for index in range(0, maxAttempts):
            try:
                header = {'authorization': f'Bearer {self.key.accessToken}'}
                if playbackRequest:
                    self.__waitForStreamRequestQuota__()

                respond = self.session.get(url, headers=header, params=params, timeout=REQUEST_TIMEOUT)

                if respond.status_code == 429:
                    if index >= RATE_LIMIT_MAX_ATTEMPTS - 1:
                        raise self.__httpError__("Get operation", respond)
                    delay = self.__retryAfter__(respond, index)
                    print(f"Too many requests, waiting {delay:g} seconds before retry.")
                    respond.close()
                    time.sleep(delay)
                    continue

                if respond.status_code == 401 and self.__isAssetNotReady__(respond):
                    delay = min(5 * (index + 1), 30)
                    print(f"Asset not ready for playback, waiting {delay:g} seconds before retry.")
                    respond.close()
                    time.sleep(delay)
                    continue

                if respond.status_code == 401 and not refreshedToken and self.__refreshSavedAccessToken__():
                    refreshedToken = True
                    continue

                if respond.status_code != 200:
                    raise self.__httpError__("Get operation", respond)

                result = json.loads(respond.text)
                if 'status' not in result:
                    return result

                if 'userMessage' in result and result['userMessage'] is not None:
                    errmsg += result['userMessage']
                break
            except TidalApiError as e:
                if self.__isNonRetryableTidalApiError__(e, playbackRequest) or index >= maxAttempts - 1:
                    raise e
            except Exception as e:
                if index >= maxAttempts - 1 and respond is not None:
                    errmsg += respond.text

        if respond is not None and self.__isAssetNotReady__(respond):
            body = self.__responseBody__(respond)
            message = body.get('userMessage') or 'Asset is not ready for playback'
            raise Exception(f"{errmsg}{message}")
        raise Exception(errmsg)

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
            except Exception as e:
                last_error = e
                logging.debug("Playback request failed for %s%s: %s", base, path, e)
                if self.__isPlaybackBlockedError__(e):
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
            if total > 0 and total <= len(ret):
                return ret

            ret += data["items"]
            num = len(data["items"])
            if num < 50:
                break
            params['offset'] += num
        return ret

    def __getResolutionList__(self, url):
        ret = []
        response = self.session.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        txt = response.content.decode('utf-8')
        # array = txt.split("#EXT-X-STREAM-INF")
        array = txt.split("#")
        for item in array:
            if "RESOLUTION=" not in item:
                continue
            if "EXT-X-STREAM-INF:" not in item:
                continue
            stream = VideoStreamUrl()
            stream.codec = aigpy.string.getSub(item, "CODECS=\"", "\"")
            stream.m3u8Url = "http" + aigpy.string.getSubOnlyStart(item, "http").strip()
            stream.resolution = aigpy.string.getSub(item, "RESOLUTION=", "http").strip()
            stream.resolution = stream.resolution.split(',')[0]
            stream.resolutions = stream.resolution.split("x")
            ret.append(stream)
        return ret

    def __post__(self, path, data, auth=None, urlpre='https://auth.tidal.com/v1/oauth2'):
        for index in range(3):
            try:
                response = self.session.post(urlpre + path, data=data, auth=auth, timeout=REQUEST_TIMEOUT)
                try:
                    return response.json()
                except ValueError:
                    detail = response.text[:200].replace("\n", " ")
                    raise Exception(
                        f"Unexpected HTTP {response.status_code} response from Tidal auth endpoint: {detail}"
                    )
            except Exception as e:
                if index == 2:
                    raise e

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
        return "http://" + self.key.verificationUrl + "/" + self.key.userCode

    def checkAuthStatus(self) -> bool:
        data = {
            'client_id': self.apiKey['clientId'],
            'device_code': self.key.deviceCode,
            'grant_type': 'urn:ietf:params:oauth:grant-type:device_code',
            'scope': 'r_usr w_usr w_sub'
        }
        if not aigpy.string.isNull(self.apiKey.get('clientSecret')):
            data['client_secret'] = self.apiKey['clientSecret']
        result = self.__post__('/token', data)
        if result.get('error') in ('authorization_pending', 'slow_down'):
            return False
        if 'status' in result and result['status'] != 200:
            if result['status'] == 400 and result.get('sub_status') == 1002:
                return False
            elif result.get('error') in ('authorization_pending', 'slow_down'):
                return False
            else:
                raise Exception("Error while checking for authorization. Trying again...")

        # if auth is successful:
        self.key.userId = result['user']['userId']
        self.key.countryCode = result['user']['countryCode']
        self.key.accessToken = result['access_token']
        self.key.refreshToken = result['refresh_token']
        self.key.expiresIn = result['expires_in']
        return True

    def verifyAccessToken(self, accessToken) -> bool:
        header = {'authorization': 'Bearer {}'.format(accessToken)}
        result = self.session.get('https://api.tidal.com/v1/sessions', headers=header, timeout=REQUEST_TIMEOUT).json()

        if 'status' in result and result['status'] != 200:
            return False
        return True

    def refreshAccessToken(self, refreshToken) -> bool:
        data = {
            'client_id': self.apiKey['clientId'],
            'refresh_token': refreshToken,
            'grant_type': 'refresh_token',
            'scope': 'r_usr w_usr w_sub'
        }
        if not aigpy.string.isNull(self.apiKey.get('clientSecret')):
            data['client_secret'] = self.apiKey['clientSecret']
        result = self.__post__('/token', data)
        if 'status' in result and result['status'] != 200:
            return False

        # if auth is successful:
        self.key.userId = result['user']['userId']
        self.key.countryCode = result['user']['countryCode']
        self.key.accessToken = result['access_token']
        self.key.refreshToken = result.get('refresh_token', refreshToken)
        self.key.expiresIn = result['expires_in']
        return True

    def loginByAccessToken(self, accessToken, userid=None):
        header = {'authorization': 'Bearer {}'.format(accessToken)}
        result = self.session.get('https://api.tidal.com/v1/sessions', headers=header, timeout=REQUEST_TIMEOUT).json()
        if 'status' in result and result['status'] != 200:
            raise Exception("Login failed!")

        if not aigpy.string.isNull(userid):
            if str(result['userId']) != str(userid):
                raise Exception("User mismatch! Please use your own accesstoken.", )

        self.key.userId = result['userId']
        self.key.countryCode = result['countryCode']
        self.key.accessToken = accessToken

        return

    def getAlbum(self, id) -> Album:
        return aigpy.model.dictToModel(self.__get__('albums/' + str(id)), Album())

    def getPlaylist(self, id) -> Playlist:
        return aigpy.model.dictToModel(self.__get__('playlists/' + str(id)), Playlist())

    def getPlaylistSelf(self) -> List[Playlist]:
        ret = self.__get__(f'users/{self.key.userId}/playlists')
        playlists = []
        for item in ret['items']:
            playlists.append(aigpy.model.dictToModel(item, Playlist()))
        return playlists

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

    def getSearchResultItems(self, result: SearchResult, type: Type):
        if type == Type.Track:
            return result.tracks.items
        if type == Type.Video:
            return result.videos.items
        if type == Type.Album:
            return result.albums.items
        if type == Type.Artist:
            return result.artists.items
        if type == Type.Playlist:
            return result.playlists.items
        return []

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
            if item['type'] == 'track' and item['item']['streamReady']:
                tracks.append(aigpy.model.dictToModel(item['item'], Track()))
            elif item['type'] == 'video':
                videos.append(aigpy.model.dictToModel(item['item'], Video()))
        return tracks, videos

    def getArtistAlbums(self, id, includeEP=False):
        data = self.__getItems__(f'artists/{str(id)}/albums')
        albums = list(aigpy.model.dictToModel(item, Album()) for item in data)
        if not includeEP:
            return albums

        data = self.__getItems__(f'artists/{str(id)}/albums', {"filter": "EPSANDSINGLES"})
        albums += list(aigpy.model.dictToModel(item, Album()) for item in data)
        return albums

    def getArtistVideos(self, id):
        data = self.__getItems__(f'artists/{str(id)}/videos')
        videos = []
        for item in data:
            if isinstance(item, dict) and item.get('type') == 'video' and 'item' in item:
                item = item['item']
            videos.append(aigpy.model.dictToModel(item, Video()))
        return videos

    # from https://github.com/Dniel97/orpheusdl-tidal/blob/master/interface.py#L582
    def parse_mpd(self, xml: bytes) -> list:
        # Removes default namespace definition, don't do that!
        xml = re.sub(r'xmlns="[^"]+"', '', xml, count=1)
        root = ElementTree.fromstring(xml)

        # List of AudioTracks
        tracks = []

        for period in root.findall('Period'):
            for adaptation_set in period.findall('AdaptationSet'):
                for rep in adaptation_set.findall('Representation'):
                    # Check if representation is audio
                    content_type = adaptation_set.get('contentType')
                    if content_type != 'audio':
                        raise ValueError('Only supports audio MPDs!')

                    # Codec checks
                    codec = rep.get('codecs').upper()
                    if codec.startswith('MP4A'):
                        codec = 'AAC'

                    # Segment template
                    seg_template = rep.find('SegmentTemplate')
                    # Add init file to track_urls
                    track_urls = [seg_template.get('initialization')]
                    start_number = int(seg_template.get('startNumber') or 1)

                    # https://dashif-documents.azurewebsites.net/Guidelines-TimingModel/master/Guidelines-TimingModel.html#addressing-explicit
                    # Also see example 9
                    seg_timeline = seg_template.find('SegmentTimeline')
                    if seg_timeline is not None:
                        seg_time_list = []
                        cur_time = 0

                        for s in seg_timeline.findall('S'):
                            # Media segments start time
                            if s.get('t'):
                                cur_time = int(s.get('t'))

                            # Segment reference
                            for i in range((int(s.get('r') or 0) + 1)):
                                seg_time_list.append(cur_time)
                                # Add duration to current time
                                cur_time += int(s.get('d'))

                        # Create list with $Number$ indices
                        seg_num_list = list(range(start_number, len(seg_time_list) + start_number))
                        # Replace $Number$ with all the seg_num_list indices
                        track_urls += [seg_template.get('media').replace('$Number$', str(n)) for n in seg_num_list]

                    tracks.append(track_urls)
        return tracks

    def __openApiFormatsForQuality__(self, quality: AudioQuality):
        if quality == AudioQuality.Max:
            return ['FLAC_HIRES', 'FLAC']
        if quality == AudioQuality.Master:
            return ['FLAC_HIRES', 'FLAC']
        if quality == AudioQuality.HiFi:
            return ['FLAC']
        return ['FLAC']

    def __openApiManifestUsages__(self):
        return ('DOWNLOAD', 'PLAYBACK')

    def __getOpenApiTrackManifest__(self, id, formats, usages=None):
        last_error = None
        for usage in usages or self.__openApiManifestUsages__():
            try:
                return self.__getOpenApiTrackManifestOnce__(id, formats, usage)
            except TidalApiError as e:
                last_error = e
                if e.statusCode in (403, 404, 405) and usage != self.__openApiManifestUsages__()[-1]:
                    logging.debug(
                        "Track manifest usage=%s unavailable, trying next usage: %s",
                        usage,
                        e,
                    )
                    continue
                raise
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
        refreshedToken = False
        rateLimitAttempts = 0
        light_quota = bool(self._playbackBlockedParams)
        for attempt in range(PLAYBACK_ASSET_NOT_READY_ATTEMPTS):
            self.__waitForStreamRequestQuota__(light=light_quota)
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
                rateLimitAttempts += 1
                if rateLimitAttempts >= RATE_LIMIT_MAX_ATTEMPTS:
                    raise self.__httpError__("Track manifest request", response)
                delay = self.__retryAfter__(response, rateLimitAttempts - 1)
                print(f"Too many requests, waiting {delay:g} seconds before retry.")
                response.close()
                time.sleep(delay)
                continue

            if response.status_code == 401 and self.__isAssetNotReady__(response):
                delay = min(5 * (attempt + 1), 30)
                print(f"Asset not ready for playback, waiting {delay:g} seconds before retry.")
                response.close()
                time.sleep(delay)
                continue

            if response.status_code == 401 and not refreshedToken and self.__refreshSavedAccessToken__():
                refreshedToken = True
                response.close()
                continue

            break

        if response is None or response.status_code != 200:
            raise self.__httpError__("Track manifest request", response)

        data = response.json()
        return data.get('data', {}).get('attributes', {})

    def __openApiFlacSoundQuality__(self, formats):
        available = set(formats or [])
        if 'FLAC_HIRES' in available:
            return 'HI_RES_LOSSLESS'
        if 'FLAC' in available:
            return 'LOSSLESS'
        return None

    def __getAtmosStreamUrl__(self, id):
        attrs = self.__getOpenApiTrackManifest__(id, ['EAC3_JOC'])
        formats = attrs.get('formats') or []
        if 'EAC3_JOC' not in formats:
            raise TidalStreamUnavailable("Dolby Atmos stream is not available for this track.")

        uri = attrs.get('uri') or ''
        if ',' not in uri:
            raise TidalStreamUnavailable("Dolby Atmos manifest is empty.")

        xmldata = base64.b64decode(uri.split(',', 1)[1]).decode('utf-8')
        ret = StreamUrl()
        ret.trackid = id
        ret.soundQuality = 'DOLBY_ATMOS'
        ret.manifestMimeType = 'application/dash+xml'
        ret.codec = aigpy.string.getSub(xmldata, 'codecs="', '"')
        ret.encryptionKey = ''
        ret.urls = self.parse_mpd(xmldata)[0]
        ret.container = 'mp4'
        if len(ret.urls) > 0:
            ret.url = ret.urls[0]
        return ret

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

        xmldata = base64.b64decode(uri.split(',', 1)[1]).decode('utf-8')
        ret = StreamUrl()
        ret.trackid = id
        ret.soundQuality = sound_quality
        ret.manifestMimeType = 'application/dash+xml'
        ret.codec = aigpy.string.getSub(xmldata, 'codecs="', '"')
        ret.encryptionKey = ''
        ret.urls = self.parse_mpd(xmldata)[0]
        ret.container = 'mp4'
        if len(ret.urls) > 0:
            ret.url = ret.urls[0]
        return ret

    def __getAudioStreamUrlForQuality__(self, id, quality: AudioQuality):
        chain = []
        if quality == AudioQuality.Atmos:
            chain.append(lambda: self.__getAtmosStreamUrl__(id))
        chain.append(lambda: self.__getStandardStreamUrl__(id, quality))
        if quality in (AudioQuality.HiFi, AudioQuality.Max, AudioQuality.Master):
            chain.append(lambda q=quality: self.__getOpenApiFlacStreamUrl__(id, q))

        last_error = None
        for index, getter in enumerate(chain):
            try:
                return getter()
            except Exception as e:
                last_error = e
                if index < len(chain) - 1 and self.__shouldSkipOpenApiFallback__(e):
                    break
        raise last_error

    def __audioQualityParam__(self, quality: AudioQuality):
        if quality == AudioQuality.Normal:
            return "LOW"
        if quality == AudioQuality.High:
            return "HIGH"
        if quality == AudioQuality.HiFi:
            return "LOSSLESS"
        if quality == AudioQuality.Max:
            return "HI_RES_LOSSLESS"
        return "HI_RES"

    def __qualityFallbacks__(self, quality: AudioQuality):
        ladder = [
            AudioQuality.Atmos,
            AudioQuality.Max,
            AudioQuality.Master,
            AudioQuality.HiFi,
            AudioQuality.High,
            AudioQuality.Normal,
        ]
        if quality not in ladder:
            return [quality]
        return ladder[ladder.index(quality):]

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
        if isinstance(error, TidalStreamUnavailable):
            return "requested format is unavailable"
        if isinstance(error, TidalApiError):
            if 'CLIENT_NOT_ENTITLED' in error.errorCodes:
                return "requested format is not allowed for this account or track"
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
        if self.__isRateLimitError__(error):
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
        if audio_param in self._playbackBlockedParams:
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
            return ret
        elif "dash+xml" in resp.manifestMimeType:
            xmldata = base64.b64decode(resp.manifest).decode('utf-8')
            ret = StreamUrl()
            ret.trackid = resp.trackid
            ret.soundQuality = resp.audioQuality
            ret.manifestMimeType = resp.manifestMimeType
            ret.codec = aigpy.string.getSub(xmldata, 'codecs="', '"')
            ret.encryptionKey = ""  # manifest['keyId'] if 'keyId' in manifest else ""
            ret.urls = self.parse_mpd(xmldata)[0]
            ret.container = "mp4"
            if len(ret.urls) > 0:
                ret.url = ret.urls[0]
            return ret

        raise Exception("Can't get the streamUrl, type is " + resp.manifestMimeType)

    def getStreamUrlByPriority(self, id, qualities):
        priority = []
        for quality in qualities or []:
            normalized = self.__normalizeAudioQuality__(quality)
            if normalized is not None and normalized not in priority:
                priority.append(normalized)
        if not priority:
            priority = [AudioQuality.Normal]

        lastError = None
        requestedQuality = priority[0]
        for index, item in enumerate(priority):
            try:
                stream = self.__getAudioStreamUrlForQuality__(id, item)
                mismatch = self.__streamQualityMismatch__(stream, item)
                if mismatch is not None:
                    lastError = mismatch
                    if index == len(priority) - 1:
                        raise mismatch
                    continue
                return self.__annotateStreamFallback__(stream, requestedQuality, item, lastError)
            except Exception as e:
                lastError = e
                if index == len(priority) - 1 or not self.__isManifestFallbackError__(e):
                    raise
        raise lastError

    def getStreamUrl(self, id, quality: AudioQuality):
        lastError = None
        qualities = self.__qualityFallbacks__(quality)
        for index, item in enumerate(qualities):
            try:
                stream = self.__getAudioStreamUrlForQuality__(id, item)
                mismatch = self.__streamQualityMismatch__(stream, item)
                if mismatch is not None:
                    lastError = mismatch
                    if index == len(qualities) - 1:
                        raise mismatch
                    continue
                return self.__annotateStreamFallback__(stream, quality, item, lastError)
            except Exception as e:
                lastError = e
                if index == len(qualities) - 1 or not self.__isManifestFallbackError__(e):
                    raise
        raise lastError

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

    def getCoverData(self, sid, width="320", height="320"):
        url = self.getCoverUrl(sid, width, height)
        try:
            return self.session.get(url, timeout=REQUEST_TIMEOUT).content
        except:
            return ''

    def getArtistsName(self, artists=[]):
        array = list(item.name for item in artists)
        return ", ".join(array)

    def getFlag(self, data, type: Type, short=True, separator=" / "):
        master = False
        atmos = False
        explicit = False
        if type == Type.Album or type == Type.Track:
            if data.audioQuality == "HI_RES":
                master = True
            if type == Type.Album and "DOLBY_ATMOS" in (data.audioModes or []):
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

    def getByString(self, string):
        if aigpy.string.isNull(string):
            raise Exception("Please enter something.")

        obj = None
        etype, sid = self.parseUrl(string)
        for index, item in enumerate(Type):
            if etype != Type.Null and etype != item:
                continue
            if item == Type.Null:
                continue
            try:
                obj = self.getTypeData(sid, item)
                return item, obj
            except:
                continue

        raise Exception("No result.")

# Singleton
TIDAL_API = TidalAPI()
