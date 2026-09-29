#!/usr/bin/env python
# -*- encoding: utf-8 -*-
'''
@File    :   download.py
@Time    :   2020/11/08
@Author  :   Yaronzz
@Version :   1.0
@Contact :   yaronhuang@foxmail.com
@Desc    :
'''

from .runtime import check_cancelled, DownloadCancelled, sleep as cancellable_sleep
import logging
import json
import os
import shutil
import subprocess
import time
import tempfile
from contextlib import ExitStack
from functools import wraps
from contextvars import copy_context
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import BoundedSemaphore, Lock, local
from urllib.parse import urljoin

import aigpy
import requests

from .decryption import decrypt_file, decrypt_security_token
from .enums import AudioQuality, Type
from .model import Album, Lyrics, Playlist, Track, Video
from .paths import downloadRoot, getAlbumPath, getTrackPath, getVideoPath
from .printf import Printf
from .settings import SETTINGS
from .tidal import TIDAL_API
from .manifests import MAX_MANIFEST_BYTES, hls_segments
from .http import retry_delay, response_bytes
from .transfer_state import (
    prepare_transfer, complete_transfer, audio_identity, video_identity,
    record_completion, is_completed, completion_state,
)
from .runtime import run_process, redact, output_lock
from .network_policy import UnsafeMediaUrl, validate_media_url


DOWNLOAD_TIMEOUT = (5, 60)
DEFAULT_PART_SIZE = 1048576
VIDEO_THREAD_COUNT = 8
MAX_MEDIA_CONNECTIONS = 8
DOWNLOAD_RETRIES = 4
DOWNLOAD_CHUNK_SIZE = 256 * 1024
MAX_ARTWORK_BYTES = 16 * 1024 * 1024
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
FAILED_TRACKS_FILE = "failed-tracks.txt"
failed_track_log_lock = Lock()
download_session_state = local()
media_connection_slots = BoundedSemaphore(MAX_MEDIA_CONNECTIONS)


class _PublicMediaAuth(requests.auth.AuthBase):
    """Do not attach account or automatic .netrc credentials to media URLs."""

    def __call__(self, request):
        request.headers.pop('Authorization', None)
        return request


def _connectionLimited(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        acquired = False
        try:
            while not acquired:
                check_cancelled()
                acquired = media_connection_slots.acquire(timeout=0.1)
            check_cancelled()
            return function(*args, **kwargs)
        finally:
            if acquired:
                media_connection_slots.release()
    return wrapped


def _httpSession():
    session = getattr(download_session_state, "session", None)
    if session is None:
        session = requests.Session()
        session.auth = _PublicMediaAuth()
        # Request/transfer loops own retries so cancellation and attempt limits
        # apply to every network attempt, including connection failures. Each
        # thread owns its session and makes only one request at a time.
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=MAX_MEDIA_CONNECTIONS, pool_maxsize=1, max_retries=0,
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        download_session_state.session = session
    return session


def _removeFile(path):
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError as e:
        logging.warning("Unable to remove temporary file %s: %s", path, e)


def _removeDir(path):
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
    except OSError as e:
        logging.warning("Unable to remove temporary directory %s: %s", path, e)


def _failedTrackLogPath():
    return os.path.join(downloadRoot(), FAILED_TRACKS_FILE)


def _tidalTrackUrl(track):
    return f"https://tidal.com/browse/track/{getattr(track, 'id', '')}"


def _oneLine(value):
    return " ".join(str(value).split())


def _logFailedTrack(track, album=None, playlist=None, reason=""):
    track_id = getattr(track, 'id', None)
    if track_id is None:
        return

    try:
        path = _failedTrackLogPath()
        _ensureParentDir(path)
        context = []
        album_title = getattr(album, 'title', None)
        playlist_title = getattr(playlist, 'title', None)
        if album_title:
            context.append(f"album={_oneLine(album_title)}")
        if playlist_title:
            context.append(f"playlist={_oneLine(playlist_title)}")

        title = getattr(track, 'title', None) or str(track_id)
        parts = [
            time.strftime("%Y-%m-%d %H:%M:%S"),
            f"track={_oneLine(title)}",
            f"id={track_id}",
        ]
        parts.extend(context)
        if reason:
            parts.append(f"reason={_oneLine(reason)}")
        entry = "# " + " | ".join(parts) + "\n" + _tidalTrackUrl(track) + "\n"

        with failed_track_log_lock:
            with open(path, "a", encoding="utf-8") as output:
                output.write(redact(entry))
    except DownloadCancelled:
        raise
    except Exception as e:
        logging.warning("Unable to log failed track %s: %s", track_id, e)


def _ensureParentDir(path):
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def _retryDelay(response, attempt):
    return retry_delay(response, default=min(2 ** attempt, 20), cap=60)


def _shouldRetryDownload(error=None):
    """Retry connection failures and transient HTTP statuses, not 404/403/etc."""
    status = getattr(getattr(error, "response", None), "status_code", None)
    if status is None:
        return True
    return status in RETRYABLE_STATUS_CODES


def _httpRequest(method, url, attempts=DOWNLOAD_RETRIES, **kwargs):
    follow_redirects = bool(kwargs.pop('allow_redirects', False))
    last_error = None
    for attempt in range(attempts):
        check_cancelled()
        response = None
        try:
            current_url = url
            for _ in range(6):
                validate_media_url(current_url)
                response = _httpSession().request(
                    method, current_url, timeout=DOWNLOAD_TIMEOUT, allow_redirects=False, **kwargs
                )
                if not follow_redirects or response.status_code not in (301, 302, 303, 307, 308):
                    break
                location = response.headers.get('Location')
                if not location:
                    break
                next_url = urljoin(current_url, location)
                validate_media_url(next_url)
                if current_url.lower().startswith('https:') and not next_url.lower().startswith('https:'):
                    raise UnsafeMediaUrl('Media redirects may not downgrade HTTPS to HTTP.')
                response.close()
                response = None
                current_url = next_url
            else:
                raise requests.TooManyRedirects('Media URL exceeded five redirects.')
            if response.status_code in RETRYABLE_STATUS_CODES and attempt < attempts - 1:
                response.close()
                cancellable_sleep(_retryDelay(response, attempt))
                continue
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            last_error = e
            retry = attempt < attempts - 1 and _shouldRetryDownload(e)
            if response is not None:
                response.close()
            if retry:
                cancellable_sleep(_retryDelay(getattr(e, "response", None), attempt))
                continue
            raise
        except Exception:
            if response is not None:
                response.close()
            raise
    raise last_error


def _parseIntHeader(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def _contentRangeStart(response):
    contentRange = response.headers.get("Content-Range", "")
    if not contentRange.lower().startswith("bytes "):
        return None
    try:
        return int(contentRange.split(" ", 1)[1].split("-", 1)[0])
    except (IndexError, ValueError):
        return None


def _contentTotalSize(response):
    """Best-effort total object size from Content-Range or Content-Length."""
    if response is None:
        return -1
    contentRange = response.headers.get("Content-Range", "")
    if contentRange.lower().startswith("bytes ") and "/" in contentRange:
        total = contentRange.rsplit("/", 1)[-1].strip()
        if total != "*":
            size = _parseIntHeader(total)
            if size > 0:
                return size
    if response.status_code == 200:
        size = _parseIntHeader(response.headers.get("Content-Length"))
        if size > 0:
            return size
    return -1


@_connectionLimited
def _contentLength(url):
    """Probe remote size via HEAD, falling back to a 1-byte Range GET."""
    try:
        response = _httpRequest("HEAD", url, allow_redirects=True)
        try:
            size = _contentTotalSize(response)
            if size > 0:
                return size
        finally:
            response.close()
    except DownloadCancelled:
        raise
    except Exception as error:
        logging.debug("HEAD size probe failed for %s, trying ranged GET: %s", url, error)

    # Some CDNs reject HEAD; a tiny ranged GET still exposes total size.
    try:
        response = _httpRequest(
            "GET",
            url,
            allow_redirects=True,
            stream=True,
            headers={"Range": "bytes=0-0"},
        )
        try:
            size = _contentTotalSize(response)
            if size > 0:
                return size
            # A 206 Content-Length describes only the range body (often one
            # byte), not the object. Unknown totals must remain unknown.
            return -1
        finally:
            response.close()
    except DownloadCancelled:
        raise
    except Exception as error:
        logging.debug("Ranged GET size probe failed for %s: %s", url, error)
        return -1


def _remoteSize(urls):
    if isinstance(urls, str):
        urls = [urls]
    urls = list(urls or [])
    if not urls:
        return 0
    if len(urls) == 1:
        size = _contentLength(urls[0])
        return size if size > 0 else -1

    # Probe segment sizes in parallel; serial HEAD requests dominated
    # startup time for DASH tracks with many segments.
    total = 0
    with ThreadPoolExecutor(max_workers=min(8, len(urls))) as probe_pool:
        futures = [probe_pool.submit(copy_context().run, _contentLength, url) for url in urls]
        try:
            for future in as_completed(futures):
                check_cancelled()
                size = future.result()
                if size <= 0:
                    return -1
                total += size
        finally:
            for future in futures:
                future.cancel()
    return total


def _localFileSize(path):
    return aigpy.file.getSize(path) if path else 0


def _isCompleteLocalFile(path, expectedSize=-1):
    """True when ``path`` is a finished object.

    If ``expectedSize`` is known, require an exact match. If unknown, only treat
    the file as finished when there is no ``.download`` resume sidecar (used for
    multi-segment parts that already completed in a prior attempt).
    """
    size = _localFileSize(path)
    if size <= 0:
        return False
    # A leftover .download sidecar means the last transfer did not finish cleanly.
    if _localFileSize(path + ".download") > 0:
        return False
    if expectedSize > 0:
        return size == expectedSize
    return True


def _verifyLocalSize(path, expectedSize, label="download"):
    actual = _localFileSize(path)
    if actual <= 0:
        raise IOError(f"Incomplete {label}: received an empty file")
    if expectedSize is None or expectedSize <= 0:
        return actual
    if actual != expectedSize:
        raise IOError(
            f"Incomplete {label}: got {actual} bytes, expected {expectedSize}"
        )
    return actual


def _callProgressSink(sink, methodName, value):
    """Invoke a progress callback without letting UI errors abort a download.

    Progress sinks are caller-supplied (CLI bar, GUI reporter, test doubles);
    a broken sink is logged at debug level and otherwise ignored.
    """
    if sink is None:
        return
    method = getattr(sink, methodName, None)
    if method is None:
        return
    try:
        method(value)
    except DownloadCancelled:
        raise
    except Exception as error:
        logging.debug("Progress sink %s.%s failed: %s", type(sink).__name__, methodName, error)


def _setUserProgressMax(userProgress, size):
    if size <= 0:
        return
    _callProgressSink(userProgress, "setMaxNum", size)


def _noteProgress(progress, userProgress, size, progressLock=None):
    if size <= 0:
        return
    if progressLock is not None:
        with progressLock:
            _callProgressSink(progress, "addCurCount", size)
            _callProgressSink(userProgress, "addCurNum", size)
        return
    _callProgressSink(progress, "addCurCount", size)
    _callProgressSink(userProgress, "addCurNum", size)


@_connectionLimited
def _downloadSingleUrl(
        url,
        outputPath,
        progress=None,
        userProgress=None,
        chunkSize=DOWNLOAD_CHUNK_SIZE,
        progressLock=None,
        expectedSize=-1,
        allowUnknownSizeReuse=False,
        reuseExisting=True,
        on_size=None):
    """Download one CDN URL to outputPath with HTTP Range resume.

    Partial progress is kept in ``outputPath + '.download'`` until the transfer
    finishes, then moved into place with ``os.replace`` so callers never see a
    half-written final file. When ``expectedSize`` or response headers expose a
    total size, the finished file is verified before it is promoted.
    """
    # When expectedSize is known, require an exact match. Multi-segment parts may
    # also reuse a finished object when size is unknown (prior successful segment
    # write). Top-level single-URL downloads must not skip just because a local
    # file exists — that path might be an unrelated leftover.
    if expectedSize > 0:
        reusable = _isCompleteLocalFile(outputPath, expectedSize)
    elif allowUnknownSizeReuse:
        reusable = (
            _localFileSize(outputPath) > 0
            and _localFileSize(outputPath + ".download") <= 0
        )
    else:
        reusable = False
    if reusable and reuseExisting:
        if on_size is not None:
            on_size(_localFileSize(outputPath))
        _noteProgress(
            progress, userProgress, _localFileSize(outputPath), progressLock
        )
        return _localFileSize(outputPath)

    tempOutputPath = outputPath + ".download"
    reportedBytes = 0
    lastError = None
    knownTotal = expectedSize if expectedSize and expectedSize > 0 else -1

    for attempt in range(DOWNLOAD_RETRIES):
        check_cancelled()
        resumeSize = _localFileSize(tempOutputPath)
        # Range offsets describe stored bytes, so transparent HTTP content
        # decoding must not change the byte counts used for resume.
        headers = {"Accept-Encoding": "identity"}
        if resumeSize > 0:
            headers['Range'] = f'bytes={resumeSize}-'
        response = None
        try:
            response = _httpRequest("GET", url, attempts=1, stream=True, allow_redirects=True, headers=headers)
            mode = "wb"
            if resumeSize > 0:
                rangeStart = _contentRangeStart(response)
                if response.status_code == 206 and rangeStart == resumeSize:
                    mode = "ab"
                    credit = max(resumeSize - reportedBytes, 0)
                    if credit:
                        _noteProgress(progress, userProgress, credit, progressLock)
                        reportedBytes = resumeSize
                elif response.status_code == 200:
                    # Server ignored Range and returned the full object; restart.
                    _removeFile(tempOutputPath)
                    resumeSize = 0
                    mode = "wb"
                else:
                    # Mismatched partial response: drop partial and re-GET fully.
                    response.close()
                    response = None
                    _removeFile(tempOutputPath)
                    resumeSize = 0
                    response = _httpRequest("GET", url, attempts=1, stream=True, allow_redirects=True,
                                               headers={"Accept-Encoding": "identity"})
                    mode = "wb"

            encoded = response.headers.get('Content-Encoding', 'identity').lower() not in ('', 'identity')
            if encoded and (mode == 'ab' or response.status_code != 200):
                raise ValueError('The media server returned an encoded response that cannot be resumed safely.')
            if response.status_code == 206 and _contentRangeStart(response) != resumeSize:
                raise ValueError('The media server returned an unexpected byte range.')

            # requests.iter_content transparently decodes a fresh encoded body.
            # Its Content-Length describes the compressed bytes, so it cannot
            # validate the size of the decoded file written below.
            responseTotal = -1 if encoded else _contentTotalSize(response)
            if responseTotal > 0:
                knownTotal = responseTotal
            elif response.status_code == 200 and not encoded:
                contentLength = _parseIntHeader(response.headers.get("Content-Length"))
                if contentLength > 0:
                    knownTotal = contentLength
            if knownTotal > 0 and on_size is not None:
                on_size(knownTotal)

            writtenBytes = resumeSize if mode == 'ab' else 0
            with open(tempOutputPath, mode) as output:
                for chunk in response.iter_content(chunk_size=chunkSize):
                    check_cancelled()
                    if not chunk:
                        continue
                    output.write(chunk)
                    writtenBytes += len(chunk)
                    # If Range was ignored, re-downloaded bytes must not be
                    # credited twice. Keep the reported high-water mark.
                    credit = max(writtenBytes - reportedBytes, 0)
                    _noteProgress(progress, userProgress, credit, progressLock)
                    reportedBytes += credit

            _verifyLocalSize(tempOutputPath, knownTotal, label="CDN object")
            os.replace(tempOutputPath, outputPath)
            size = _localFileSize(outputPath)
            if on_size is not None:
                on_size(size)
            return size
        except (requests.RequestException, OSError, IOError) as error:
            failed_response = getattr(error, 'response', None)
            if getattr(failed_response, 'status_code', None) == 416:
                remote_total = _contentTotalSize(failed_response)
                if remote_total > 0 and resumeSize == remote_total and knownTotal in (-1, remote_total):
                    _verifyLocalSize(tempOutputPath, remote_total)
                    os.replace(tempOutputPath, outputPath)
                    _noteProgress(progress, userProgress, max(remote_total - reportedBytes, 0), progressLock)
                    if on_size is not None:
                        on_size(remote_total)
                    return remote_total
                # A stale or overlong sidecar cannot be resumed.
                _removeFile(tempOutputPath)
                if attempt < DOWNLOAD_RETRIES - 1:
                    continue
            lastError = error
            if attempt >= DOWNLOAD_RETRIES - 1 or not _shouldRetryDownload(error):
                raise
            retry_response = failed_response if failed_response is not None else response
            delay = _retryDelay(retry_response, attempt)
            if response is not None:
                response.close()
                response = None
            cancellable_sleep(delay)
        finally:
            if response is not None:
                response.close()

    raise lastError


def _concatenateFiles(partPaths, outputPath, expectedSize=-1):
    tempOutputPath = f"{outputPath}.tmp.{os.getpid()}"
    _removeFile(tempOutputPath)
    try:
        with open(tempOutputPath, "wb") as output:
            for partPath in partPaths:
                with open(partPath, "rb") as inputFile:
                    for chunk in iter(lambda: inputFile.read(1024 * 1024), b''):
                        check_cancelled()
                        output.write(chunk)
        check_cancelled()
        _verifyLocalSize(tempOutputPath, expectedSize, label="assembled media")
        os.replace(tempOutputPath, outputPath)
    finally:
        _removeFile(tempOutputPath)


def _partsDirectory(outputPath):
    # Stable across retries so multi-segment DASH can resume after a failure.
    return f"{outputPath}.parts"


def _downloadSegment(
        url,
        partPath,
        progress=None,
        userProgress=None,
        progressLock=None,
        chunkSize=DOWNLOAD_CHUNK_SIZE,
        expectedSize=-1,
        on_size=None):
    return _downloadSingleUrl(
        url,
        partPath,
        progress=progress,
        userProgress=userProgress,
        chunkSize=chunkSize,
        progressLock=progressLock,
        expectedSize=expectedSize,
        allowUnknownSizeReuse=True,
        on_size=on_size,
    )


def _downloadUrls(
        urls,
        outputPath,
        showProgress=False,
        userProgress=None,
        threadNum=1,
        chunkSize=DOWNLOAD_CHUNK_SIZE,
        probeSize=True,
        expectedSize=None,
        sourceIdentity=None):
    urls = [url for url in (urls or []) if not aigpy.string.isNull(url)]
    if len(urls) <= 0:
        return False, "URL list is empty."

    _ensureParentDir(outputPath)
    source_matches = prepare_transfer(outputPath, urls, source_identity=sourceIdentity)

    if expectedSize is not None:
        totalSize = expectedSize
    elif probeSize:
        totalSize = _remoteSize(urls)
    else:
        totalSize = -1
    progress = None
    if totalSize > 0:
        _setUserProgressMax(userProgress, totalSize)
        if showProgress:
            progress = aigpy.progress.ProgressTool(totalSize, 15, unit="B")

    size_lock = Lock()
    object_sizes = {}

    def report_size(index, size):
        # Learn sizes from actual GETs. Do not display a misleading 100% for
        # one segment while the remaining segment sizes are still unknown.
        with size_lock:
            object_sizes[index] = size
            if len(object_sizes) == len(urls):
                _setUserProgressMax(userProgress, sum(object_sizes.values()))

    # Already-complete assembled file (e.g. decrypt failed after CDN success).
    # Only reuse when the remote size is known and matches — never skip a
    # download solely because a local file happens to exist.
    if source_matches and _isCompleteLocalFile(outputPath, totalSize):
        _noteProgress(progress, userProgress, _localFileSize(outputPath))
        _removeDir(_partsDirectory(outputPath))
        return True, ''

    if len(urls) == 1:
        try:
            _downloadSingleUrl(
                urls[0],
                outputPath,
                progress,
                userProgress,
                chunkSize,
                expectedSize=totalSize,
                reuseExisting=source_matches,
                on_size=lambda size: report_size(0, size),
            )
            complete_transfer(outputPath)
            return True, ''
        except DownloadCancelled:
            raise
        except Exception as e:
            return False, str(e)

    # Multi-segment (DASH / HLS): resumeable per-segment downloads, ordered concat.
    partsDir = _partsDirectory(outputPath)
    os.makedirs(partsDir, exist_ok=True)
    progressLock = Lock()
    workers = 1 if threadNum <= 1 else min(threadNum, len(urls))
    partPaths = [os.path.join(partsDir, f"{index:08d}.part") for index in range(len(urls))]

    try:
        if workers == 1:
            for index, (url, partPath) in enumerate(zip(urls, partPaths)):
                _downloadSegment(
                    url,
                    partPath,
                    progress,
                    userProgress,
                    None,
                    chunkSize,
                    on_size=lambda size, index=index: report_size(index, size),
                )
        else:
            with ThreadPoolExecutor(max_workers=workers) as thread_pool:
                futures = {
                    thread_pool.submit(
                        copy_context().run, _downloadSegment,
                        url,
                        partPath,
                        progress,
                        userProgress,
                        progressLock,
                        chunkSize,
                        on_size=lambda size, index=index: report_size(index, size),
                    ): index
                    for index, (url, partPath) in enumerate(zip(urls, partPaths))
                }
                try:
                    for future in as_completed(futures):
                        future.result()
                except DownloadCancelled:
                    raise
                except Exception:
                    for pending in futures:
                        pending.cancel()
                    raise

        _concatenateFiles(partPaths, outputPath, expectedSize=totalSize)
        complete_transfer(outputPath)
        _removeDir(partsDir)
        return True, ''
    except DownloadCancelled:
        raise
    except Exception as e:
        # Keep complete segments under outputPath.parts for the next attempt.
        return False, str(e)


def _downloadErrorHint(err):
    text = str(err or "").lower()
    if "playback client rejected" in text:
        return " (hint: login kept; try HiFi or --quality-priority Max,HiFi,High,Normal)"
    if any(item in text for item in ("429", "too many requests", "rate limit")):
        return " (hint: raise the request interval in settings and retry)"
    if any(item in text for item in ("4022", "client referenced", "log in again")):
        return " (hint: your saved login session is stale; log out, log in again, then retry)"
    if "prerequisite" in text:
        return (
            " (hint: this quality may be unavailable to this app for your account; "
            "set a fallback order, e.g. --quality-priority Max,HiFi,High,Normal)"
        )
    if any(item in text for item in ("403", "entitled", "not allowed", "client_not_entitled")):
        return " (hint: stream may be unavailable for this account or quality; try a lower quality/fallback order)"
    if "incomplete" in text and "expected" in text:
        return " (hint: retry the download; a partial transfer was discarded after size verification failed)"
    if any(item in text for item in ("timeout", "connection", "network", "name or service not known")):
        return " (hint: check network/VPN/proxy/firewall, or run tidekeeper --doctor)"
    if any(item in text for item in ("permission", "denied", "access is denied", "readonly")):
        return " (hint: choose a writable download folder outside protected system directories)"
    if any(item in text for item in ("no space left", "disk full", "not enough space", "quota exceeded")):
        return " (hint: check available disk space)"
    if any(item in text for item in ("not ready for streaming", "not ready for playback", "asset is not ready")):
        return " (hint: retry later, raise the request interval in settings, or try a lower quality)"
    return ""


def _encrypted(stream, srcPath, descPath):
    if aigpy.string.isNull(stream.encryptionKey):
        with open(srcPath, 'rb') as source, open(descPath, 'wb') as output:
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                check_cancelled()
                output.write(chunk)
    else:
        key, nonce = decrypt_security_token(stream.encryptionKey)
        decrypt_file(srcPath, descPath, key, nonce)


def _isFlacInM4a(stream):
    codec = (getattr(stream, 'codec', None) or '').lower()
    container = (getattr(stream, 'container', None) or '').lower()
    manifestMimeType = (getattr(stream, 'manifestMimeType', None) or '').lower()
    return 'flac' in codec and ('mp4' in container or 'dash+xml' in manifestMimeType)


def _containerFallbackPath(path):
    return path.rsplit('.', 1)[0] + '.m4a'


def _existingMediaState(path, stream):
    candidates = [path]
    if SETTINGS.saveAsFlac and _isFlacInM4a(stream):
        fallback = _containerFallbackPath(path)
        if fallback != path:
            candidates.append(fallback)
    identity = audio_identity(stream)
    for candidate in candidates:
        media_complete, metadata_complete = completion_state(candidate, identity)
        if media_complete:
            return candidate, metadata_complete
    return None, False


def _manifestMediaFacts(stream):
    return {
        key: value for key, value in {
            'quality': getattr(stream, 'soundQuality', None),
            'codec': getattr(stream, 'codec', None),
            'bitDepth': getattr(stream, 'bitDepth', None),
            'sampleRate': getattr(stream, 'sampleRate', None),
            'bandwidth': getattr(stream, 'bandwidth', None),
            'channels': getattr(stream, 'channels', None),
            'representation': getattr(stream, 'representationId', None),
            'manifestHash': getattr(stream, 'manifestHash', None),
        }.items() if value not in (None, '')
    }


def _verifyMediaQuality(path, stream):
    """Probe final audio when ffprobe is available and retain verified facts."""
    facts = _manifestMediaFacts(stream)
    ffprobe = shutil.which('ffprobe')
    if not ffprobe:
        return facts
    completed = run_process(
        [ffprobe, '-v', 'error', '-protocol_whitelist', 'file',
         '-format_whitelist', 'mov,mp4,m4a,3gp,3g2,mj2,flac,aac,ac3,eac3,mp3,ogg,mpegts',
         '-select_streams', 'a:0',
         '-show_entries', 'stream=codec_name,sample_rate,bits_per_sample,bits_per_raw_sample,channels',
         '-of', 'json', path],
        capture_output=True,
        timeout=60,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or '').strip()
        raise RuntimeError('Downloaded media failed ffprobe validation: ' + (detail or 'unknown error'))
    try:
        streams = json.loads(completed.stdout or '{}').get('streams') or []
        probed = streams[0]
    except (ValueError, IndexError, TypeError, AttributeError) as error:
        raise RuntimeError('Downloaded media contains no readable audio stream.') from error

    def integer(value):
        try:
            number = int(value)
            return number if number > 0 else None
        except (TypeError, ValueError):
            return None

    actual = {
        'codec': probed.get('codec_name'),
        'sampleRate': integer(probed.get('sample_rate')),
        'bitDepth': integer(probed.get('bits_per_raw_sample')) or integer(probed.get('bits_per_sample')),
        'channels': integer(probed.get('channels')),
        'verifiedBy': 'ffprobe',
    }
    expected_codec = str(getattr(stream, 'codec', '') or '').lower()
    actual_codec = str(actual.get('codec') or '').lower()
    if 'flac' in expected_codec and actual_codec != 'flac':
        raise RuntimeError(f'Downloaded media codec is {actual_codec or "unknown"}, expected FLAC.')
    expected_rate = integer(getattr(stream, 'sampleRate', None))
    if expected_rate and actual['sampleRate'] and actual['sampleRate'] != expected_rate:
        raise RuntimeError(
            f'Downloaded media sample rate is {actual["sampleRate"]} Hz, expected {expected_rate} Hz.'
        )
    expected_depth = integer(getattr(stream, 'bitDepth', None))
    if expected_depth and actual['bitDepth'] and actual['bitDepth'] < expected_depth:
        raise RuntimeError(
            f'Downloaded media bit depth is {actual["bitDepth"]}, expected {expected_depth}.'
        )
    facts.update({key: value for key, value in actual.items() if value not in (None, '')})
    return facts


def _exportFlacFromContainer(path, stream):
    if not SETTINGS.saveAsFlac or not _isFlacInM4a(stream):
        return path

    flacPath = path.rsplit('.', 1)[0] + '.flac'
    fallbackPath = _containerFallbackPath(path)
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        logging.warning("saveAsFlac is enabled but ffmpeg was not found; saving container as %s", fallbackPath)
        if os.path.abspath(path) != os.path.abspath(fallbackPath):
            os.replace(path, fallbackPath)
        return fallbackPath

    tempPath = f"{flacPath}.tmp.{os.getpid()}.flac"
    _removeFile(tempPath)
    try:
        completed = run_process(
            [ffmpeg, '-nostdin', '-y', '-hide_banner', '-loglevel', 'error',
             '-protocol_whitelist', 'file', '-format_whitelist', 'mov,mp4,m4a,3gp,3g2,mj2,flac',
             '-i', path, '-map', '0:a:0', '-c', 'copy', '-f', 'flac', tempPath],
            capture_output=True,
            timeout=300,
            text=True,
            check=False,
        )
        if completed.returncode != 0 or _localFileSize(tempPath) <= 0:
            detail = (completed.stderr or completed.stdout or '').strip()
            raise RuntimeError(detail or f"ffmpeg exited with code {completed.returncode}")
        os.replace(tempPath, flacPath)
        if os.path.abspath(path) != os.path.abspath(flacPath):
            _removeFile(path)
        return flacPath
    except DownloadCancelled:
        raise
    except Exception as e:
        logging.warning("Unable to export FLAC for %s: %s; saving container as %s", path, e, fallbackPath)
        if os.path.abspath(path) != os.path.abspath(fallbackPath):
            os.replace(path, fallbackPath)
        return fallbackPath
    finally:
        _removeFile(tempPath)


def _lyricsText(value):
    if value is None:
        return ''
    text = str(value)
    return text if text.strip() else ''


def _hasTimedLyrics(lyricsData):
    return bool(_lyricsText(getattr(lyricsData, 'subtitles', None)))


def _lyricsPayload(lyricsData):
    if lyricsData is None:
        return '', '', ''

    subtitles = _lyricsText(getattr(lyricsData, 'subtitles', None))
    lyrics = _lyricsText(getattr(lyricsData, 'lyrics', None))
    metadataLyrics = lyrics or subtitles

    if subtitles:
        return metadataLyrics, subtitles, '.lrc'
    if lyrics:
        return metadataLyrics, lyrics, '.txt'
    return '', '', ''


def _writeTextFile(path, content):
    _ensureParentDir(path)
    tempPath = f"{path}.tmp.{os.getpid()}"
    try:
        with open(tempPath, 'w', encoding='utf-8', newline='') as output:
            output.write(content)
        os.replace(tempPath, path)
    except DownloadCancelled:
        raise
    except Exception:
        _removeFile(tempPath)
        raise


def _writeLyricsFile(trackPath, lyricsData):
    metadataLyrics, fileLyrics, extension = _lyricsPayload(lyricsData)
    if SETTINGS.lyricFile and fileLyrics:
        lyricPath = trackPath.rsplit(".", 1)[0] + extension
        _writeTextFile(lyricPath, fileLyrics)
    return metadataLyrics


def _normalizeLyricsMatchText(value):
    return " ".join(str(value or "").casefold().split())


def _iterArtists(artists):
    # TIDAL omits `artists` for some items (aigpy then stores None) and the
    # models default to a single prototype instance, so the attribute is not
    # always an iterable list of artists (issue #38).
    if isinstance(artists, (list, tuple)):
        return [artist for artist in artists if artist is not None]
    return []


def _rawArtistNames(artists):
    return [
        str(getattr(artist, 'name', '')).strip()
        for artist in _iterArtists(artists)
        if getattr(artist, 'name', None)
    ]


def _artistNames(artists):
    return [
        _normalizeLyricsMatchText(getattr(artist, 'name', ''))
        for artist in _iterArtists(artists)
        if getattr(artist, 'name', None)
    ]


def _albumTitle(item):
    album = getattr(item, 'album', None)
    return _normalizeLyricsMatchText(getattr(album, 'title', ''))


def _lyricsCandidateScore(track, candidate):
    if getattr(candidate, 'id', None) == getattr(track, 'id', None):
        return -1

    trackTitle = _normalizeLyricsMatchText(getattr(track, 'title', ''))
    candidateTitle = _normalizeLyricsMatchText(getattr(candidate, 'title', ''))
    if trackTitle != candidateTitle:
        return -1

    trackArtists = set(_artistNames(getattr(track, 'artists', [])))
    candidateArtists = set(_artistNames(getattr(candidate, 'artists', [])))
    if not trackArtists or not candidateArtists:
        return -1

    artistOverlap = trackArtists.intersection(candidateArtists)
    if not artistOverlap:
        return -1

    score = 100 + (min(len(artistOverlap), 3) * 20)

    trackArtistOrder = _artistNames(getattr(track, 'artists', []))
    candidateArtistOrder = _artistNames(getattr(candidate, 'artists', []))
    if trackArtistOrder and candidateArtistOrder and trackArtistOrder[0] == candidateArtistOrder[0]:
        score += 15

    trackIsrc = str(getattr(track, 'isrc', '') or '').strip()
    candidateIsrc = str(getattr(candidate, 'isrc', '') or '').strip()
    if trackIsrc and candidateIsrc:
        score += 50 if trackIsrc == candidateIsrc else -5

    try:
        trackDuration = int(getattr(track, 'duration', 0) or 0)
        candidateDuration = int(getattr(candidate, 'duration', 0) or 0)
    except (TypeError, ValueError):
        trackDuration = candidateDuration = None
    if trackDuration is not None:
        durationDelta = abs(trackDuration - candidateDuration)
        if durationDelta <= 2:
            score += 20
        elif durationDelta <= 5:
            score += 10

    trackAlbum = _albumTitle(track)
    candidateAlbum = _albumTitle(candidate)
    if trackAlbum and candidateAlbum and trackAlbum == candidateAlbum:
        score += 10

    noisyAlbumWords = ('commentary', 'sing-along', 'karaoke', 'instrumental')
    if any(word in candidateAlbum for word in noisyAlbumWords):
        score -= 15

    return score


def _mergeLyrics(primary, timed):
    if primary is None:
        return timed
    if timed is None or not _hasTimedLyrics(timed):
        return primary

    def firstPresent(attribute):
        return getattr(primary, attribute, None) or getattr(timed, attribute, None)

    merged = Lyrics()
    merged.trackId = firstPresent('trackId')
    merged.lyricsProvider = firstPresent('lyricsProvider')
    merged.providerCommontrackId = firstPresent('providerCommontrackId')
    merged.providerLyricsId = firstPresent('providerLyricsId')
    merged.lyrics = _lyricsText(getattr(primary, 'lyrics', None)) or _lyricsText(getattr(timed, 'lyrics', None))
    merged.subtitles = getattr(timed, 'subtitles', None)
    return merged


def _findTimedLyricsForTrack(track):
    title = getattr(track, 'title', None)
    if aigpy.string.isNull(title):
        return None

    queries = []
    artists = _rawArtistNames(getattr(track, 'artists', []))
    for artist in artists[:5]:
        queries.append(f"{title} {artist}")
    if len(artists) > 1:
        queries.append(f"{title} {' '.join(artists[:2])}")
    queries.append(str(title))

    candidatesById = {}
    for query in dict.fromkeys(queries):
        try:
            result = TIDAL_API.search(query, Type.Track, limit=10)
            candidates = TIDAL_API.getSearchResultItems(result, Type.Track)
        except DownloadCancelled:
            raise
        except Exception as e:
            logging.info("Unable to search timed lyrics fallback for track %s: %s", getattr(track, 'id', ''), e)
            continue

        for candidate in candidates:
            candidateId = getattr(candidate, 'id', None)
            if candidateId is not None:
                candidatesById[candidateId] = candidate

    scoredCandidates = sorted(
        (
            (score, candidate)
            for candidate in candidatesById.values()
            for score in [_lyricsCandidateScore(track, candidate)]
            if score >= 0
        ),
        key=lambda item: item[0],
        reverse=True,
    )

    for score, candidate in scoredCandidates:
        try:
            lyrics = TIDAL_API.getLyrics(candidate.id)
        except DownloadCancelled:
            raise
        except Exception:
            continue
        if _hasTimedLyrics(lyrics):
            return lyrics
    return None


def _getLyricsForTrack(track):
    primary = None
    try:
        primary = TIDAL_API.getLyrics(track.id)
    except DownloadCancelled:
        raise
    except Exception as e:
        logging.info("Unable to get lyrics for track %s: %s", getattr(track, 'id', ''), e)

    if not SETTINGS.lyricFile or _hasTimedLyrics(primary):
        return primary

    return _mergeLyrics(primary, _findTimedLyricsForTrack(track))


def _saveLyricsForTrack(track, trackPath):
    try:
        return _writeLyricsFile(trackPath, _getLyricsForTrack(track))
    except DownloadCancelled:
        raise
    except Exception as e:
        logging.info("Unable to save lyrics for track %s: %s", getattr(track, 'id', ''), e)
        return ''


def _parseContributors(roleType, Contributors):
    if Contributors is None:
        return None
    try:
        return [item['name'] for item in Contributors['items'] if item['role'] == roleType]
    except (KeyError, TypeError):
        return None


def _metadataSaveError(result):
    if isinstance(result, tuple):
        if len(result) > 0 and result[0] is False:
            return str(result[1]) if len(result) > 1 else "metadata writer returned false"
        return None
    if result is False:
        return "metadata writer returned false"
    return None


def _ensureMetadataTags(tagTool):
    handle = getattr(tagTool, '_handle', None)
    if handle is not None and getattr(handle, 'tags', None) is None and hasattr(handle, 'add_tags'):
        handle.add_tags()


def _metadataArtistNames(item):
    """Return tag artist names, falling back to the item's primary artist."""
    names = _rawArtistNames(getattr(item, 'artists', None))
    if names:
        return names
    artist = getattr(item, 'artist', None)
    name = getattr(artist, 'name', None) if artist is not None else None
    return [str(name).strip()] if name else []


def _setMetaData(track: Track, album: Album, filepath, contributors, lyrics):
    obj = aigpy.tag.TagTool(filepath)
    obj.album = track.album.title
    obj.title = track.title
    if not aigpy.string.isNull(track.version):
        obj.title += f' ({track.version})'

    obj.artist = _metadataArtistNames(track)
    obj.copyright = track.copyRight
    obj.tracknumber = track.trackNumber
    obj.discnumber = track.volumeNumber
    obj.composer = _parseContributors('Composer', contributors)
    obj.isrc = track.isrc

    obj.albumartist = _metadataArtistNames(album)
    obj.date = album.releaseDate
    obj.totaldisc = int(getattr(album, 'numberOfVolumes', 0) or 0)
    obj.lyrics = lyrics
    if obj.totaldisc <= 1:
        obj.totaltrack = int(getattr(album, 'numberOfTracks', 0) or 0)
    coverpath = TIDAL_API.getCoverUrl(album.cover, "1280", "1280")
    _ensureMetadataTags(obj)
    artwork = None
    try:
        if coverpath:
            response = _httpRequest('GET', coverpath, allow_redirects=True, stream=True)
            try:
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as output:
                    artwork = output.name
                    output.write(response_bytes(response, MAX_ARTWORK_BYTES, 'Cover artwork'))
            finally:
                response.close()
        error = _metadataSaveError(obj.save(artwork or ''))
        if error is not None:
            raise RuntimeError(error)
    finally:
        if artwork:
            _removeFile(artwork)


def downloadCover(album):
    if album is None:
        return False, "Album is empty."
    path = getAlbumPath(album) + '/cover.jpg'
    url = TIDAL_API.getCoverUrl(album.cover, "1280", "1280")
    if aigpy.string.isNull(url):
        return False, "Cover URL is empty."

    check, err = _downloadUrls([url], path, SETTINGS.showProgress, threadNum=1)
    if not check:
        msg = str(err)
        Printf.err(f"DL Cover '{album.title}' failed: {msg}")
        return False, msg
    return True, ''


def _volumeNumber(item):
    try:
        return max(1, int(getattr(item, 'volumeNumber', 0) or 1))
    except (TypeError, ValueError):
        return 1


def downloadAlbumInfo(album, tracks):
    """Write the optional AlbumInfo.txt sidecar; a failure never aborts the album."""
    if album is None:
        return False

    try:
        tracks = list(tracks or [])
        path = getAlbumPath(album) + '/AlbumInfo.txt'
        infos = (
            f"[ID]          {album.id}\n"
            f"[Title]       {album.title}\n"
            f"[Artists]     {TIDAL_API.getArtistsName(album.artists)}\n"
            f"[ReleaseDate] {album.releaseDate}\n"
            f"[SongNum]     {album.numberOfTracks}\n"
            f"[Duration]    {album.duration}\n"
            "\n"
        )

        # TIDAL can omit numberOfVolumes (None/0); fall back to the volumes the
        # track list actually uses so every track is still listed.
        try:
            declaredVolumes = int(getattr(album, 'numberOfVolumes', 0) or 0)
        except (TypeError, ValueError):
            declaredVolumes = 0
        volumeCount = max(declaredVolumes, max((_volumeNumber(item) for item in tracks), default=1))
        for volumeNumber in range(1, volumeCount + 1):
            infos += f"===========CD {volumeNumber}=============\n"
            for item in tracks:
                if _volumeNumber(item) != volumeNumber:
                    continue
                infos += f"{f'[{item.trackNumber}]':<8}{item.title}\n"
        _writeTextFile(path, infos)
        return True
    except DownloadCancelled:
        raise
    except Exception as e:
        Printf.err(f"Save AlbumInfo.txt '{getattr(album, 'title', '')}' failed: {e}")
        return False


def _finalizeVideoFile(partPath, path):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError('Install ffmpeg to finalize video downloads as MP4; the downloaded parts were kept.')
    tempPath = f"{path}.tmp.{os.getpid()}.mp4"
    try:
        check_cancelled()
        completed = run_process(
            [ffmpeg, '-nostdin', '-y', '-hide_banner', '-loglevel', 'error',
             '-protocol_whitelist', 'file', '-format_whitelist', 'mov,mp4,m4a,3gp,3g2,mj2,mpegts', '-i', partPath,
             '-c', 'copy', '-movflags', '+faststart', tempPath],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=300,
        )
        check_cancelled()
        if completed.returncode != 0 or _localFileSize(tempPath) <= 0:
            detail = (completed.stderr or b'').decode('utf-8', 'replace').strip()
            raise RuntimeError('Video conversion failed: ' + (detail or 'ffmpeg produced no output'))
        os.replace(tempPath, path)
        _removeFile(partPath)
        return path
    finally:
        _removeFile(tempPath)


def downloadVideo(video: Video, album: Album = None, playlist: Playlist = None, userProgress=None):
    title = getattr(video, 'title', None) or str(getattr(video, 'id', 'unknown'))
    partPath = ''
    destination = ExitStack()
    try:
        check_cancelled()
        path = getVideoPath(video, album, playlist)
        destination.enter_context(output_lock(os.path.splitext(path)[0]))
        identity = video_identity(video, SETTINGS.videoQuality)
        if SETTINGS.checkExist and is_completed(path, identity):
            Printf.success(title + ' (skip:already exists!)')
            return True, ''
        stream = TIDAL_API.getVideoStreamUrl(video.id, SETTINGS.videoQuality)
        partPath = path + '.part'

        if userProgress is not None:
            userProgress.updateStream(stream)
        Printf.video(video, stream)
        logging.info("[DL Video] name=%s url=%s", aigpy.path.getFileName(path), stream.m3u8Url)

        _ensureParentDir(path)

        response = _httpRequest("GET", stream.m3u8Url, allow_redirects=True, stream=True)
        try:
            m3u8content = response_bytes(response, MAX_MANIFEST_BYTES, 'HLS manifest')
            manifest_url = response.url or stream.m3u8Url
            if not m3u8content:
                Printf.err(f"DL Video '{title}' failed: the video playlist was empty.")
                return False, "Video playlist was empty."
        finally:
            response.close()

        urls = hls_segments(m3u8content, manifest_url)
        if len(urls) <= 0:
            Printf.err(f"DL Video '{title}' failed: the video playlist has no segments.")
            return False, "Video playlist has no segments."

        check, msg = _downloadUrls(
            urls,
            partPath,
            SETTINGS.showProgress,
            userProgress,
            VIDEO_THREAD_COUNT,
            probeSize=False,
            sourceIdentity=identity,
        )
        if check:
            path = _finalizeVideoFile(partPath, path)
            record_completion(path, identity)
            _removeFile(partPath + '.source.json')
            Printf.success(title)
            return True, ''
        else:
            Printf.err(f"DL Video '{title}' failed: {msg}")
            return False, msg
    except DownloadCancelled:
        raise
    except Exception as e:
        Printf.err(f"DL Video '{title}' failed: {e}")
        return False, str(e)
    finally:
        destination.close()


def _getTrackStream(track_id):
    priority = SETTINGS.getDownloadAudioQualityPriority()
    return TIDAL_API.getStreamUrlByPriority(track_id, priority)


def _wantsAtmosDownload():
    return any(quality == AudioQuality.Atmos for quality in SETTINGS.getDownloadAudioQualityPriority())


def _resolveTrackForAtmosDownload(track: Track, album=None):
    """Swap stereo catalog IDs for Atmos twins when Atmos quality is requested.

    Covers album, track, playlist, and mix paths — not only start_track().
    """
    if track is None or not _wantsAtmosDownload():
        return track, album
    if TIDAL_API._hasAtmosMode(track):
        return track, album

    atmos = TIDAL_API.findAtmosTrackVariant(track)
    if atmos is None or str(getattr(atmos, 'id', '')) == str(getattr(track, 'id', '')):
        return track, album

    Printf.info(
        f"Using Dolby Atmos track {atmos.id} "
        f"(stereo catalog id was {track.id})."
    )

    atmos_album = album
    atmos_album_id = getattr(getattr(atmos, 'album', None), 'id', None)
    album_id = getattr(album, 'id', None) if album is not None else None
    if atmos_album_id is not None and str(atmos_album_id) != str(album_id or ''):
        try:
            atmos_album = TIDAL_API.getAlbum(atmos_album_id)
        except DownloadCancelled:
            raise
        except Exception:
            atmos_album = album
    return atmos, atmos_album


def _ensureTrackStreamable(track):
    if getattr(track, 'allowStreaming', None) is False:
        raise Exception("Track is not available for streaming on this account.")
    if getattr(track, 'streamReady', None) is False:
        raise Exception("Track is not ready for streaming yet. Try again later.")


def downloadTrack(track: Track, album=None, playlist=None, userProgress=None, partSize=DEFAULT_PART_SIZE):
    """Resolve stream → download CDN bytes → decrypt → tag.

    Pipeline:
      1. Quality priority + OpenAPI/playback fallback (``getStreamUrlByPriority``)
      2. Skip only when a completion receipt matches the file and requested media
      3. Download to ``path.part`` with Range resume / multi-segment concat
      4. AES-CTR decrypt when encryptionKey is present (chunked, not whole-file)
      5. Optional ffmpeg FLAC remux, lyrics sidecar, metadata tags
    """
    title = getattr(track, 'title', None) or str(getattr(track, 'id', 'unknown'))
    partPath = ''
    processingPath = ''
    destination = ExitStack()
    try:
        check_cancelled()
        track, album = _resolveTrackForAtmosDownload(track, album)
        title = getattr(track, 'title', None) or str(getattr(track, 'id', 'unknown'))
        _ensureTrackStreamable(track)
        stream = _getTrackStream(track.id)
        stream.trackid = track.id
        path = getTrackPath(track, stream, album, playlist)
        destination.enter_context(output_lock(os.path.splitext(path)[0]))
        partPath = path + '.part'
        partsDir = _partsDirectory(partPath)

        if SETTINGS.showTrackInfo and not SETTINGS.multiThread:
            Printf.track(track, stream)

        if userProgress is not None:
            userProgress.updateStream(stream)

        # Inspect receipts once for both skipping and metadata-only repair.
        existingPath, metadataComplete = _existingMediaState(path, stream)
        if SETTINGS.checkExist and existingPath is not None and metadataComplete:
            if SETTINGS.lyricFile:
                _saveLyricsForTrack(track, existingPath)
            Printf.success(aigpy.path.getFileName(existingPath) + " (skip:already exists!)")
            return True, ''

        # A completed audio file whose tag write failed is repaired in place;
        # never fetch or decrypt the media bytes a second time just for tags.
        if existingPath is not None and not metadataComplete:
            try:
                contributors = TIDAL_API.getTrackContributors(track.id)
            except DownloadCancelled:
                raise
            except Exception:
                contributors = None
            lyrics = _saveLyricsForTrack(track, existingPath)
            try:
                _setMetaData(track, album, existingPath, contributors, lyrics)
                facts = _verifyMediaQuality(existingPath, stream)
                record_completion(existingPath, audio_identity(stream), media_facts=facts)
                _removeFile(partPath)
                _removeFile(partPath + '.source.json')
                _removeDir(partsDir)
                Printf.success(title + ' (metadata repaired)')
            except DownloadCancelled:
                raise
            except Exception as error:
                # A failed tagger may have partially touched the container.
                # Re-probe before preserving it as media-complete.
                facts = _verifyMediaQuality(existingPath, stream)
                record_completion(
                    existingPath, audio_identity(stream), metadata_complete=False, media_facts=facts
                )
                logging.warning("Unable to repair metadata for %s: %s", existingPath, error)
                Printf.info(f"Downloaded '{title}', but metadata tagging is still incomplete: {str(error)}")
                if hasattr(userProgress, 'note_warning'):
                    userProgress.note_warning(f'Metadata could not be saved for {title}')
            return True, ''

        # download
        logging.info("[DL Track] name=%s url=%s", aigpy.path.getFileName(path), stream.url)

        _ensureParentDir(path)

        # Do not issue a HEAD/ranged-GET size probe for every DASH object.
        # Each real GET supplies Content-Length/Content-Range for per-object
        # verification, and the completed-transfer marker records the final
        # assembled size for safe local reuse. This roughly halves CDN request
        # count for segmented audio and avoids an up-front parallel burst.
        check, err = _downloadUrls(
            stream.urls, partPath, SETTINGS.showProgress and not SETTINGS.multiThread,
            userProgress, SETTINGS.segmentsPerTrack if SETTINGS.multiThread else 1,
            max(int(partSize), 64 * 1024), probeSize=False,
            sourceIdentity=audio_identity(stream),
        )
        if not check:
            _logFailedTrack(track, album, playlist, err)
            Printf.err(f"DL Track '{title}' failed: {str(err)}{_downloadErrorHint(err)}")
            return False, str(err)

        # encrypted -> decrypt and remove encrypted file.
        # On failure, the outer handler keeps a complete partPath for retry.
        stem, extension = os.path.splitext(path)
        processingPath = f'{stem}.processing.{os.getpid()}{extension}'
        _encrypted(stream, partPath, processingPath)
        _removeDir(partsDir)
        processingPath = _exportFlacFromContainer(processingPath, stream)
        path = stem + os.path.splitext(processingPath)[1]

        # contributors
        try:
            contributors = TIDAL_API.getTrackContributors(track.id)
        except DownloadCancelled:
            raise
        except Exception:
            contributors = None

        lyrics = _saveLyricsForTrack(track, path)

        metadata_complete = True
        try:
            _setMetaData(track, album, processingPath, contributors, lyrics)
        except DownloadCancelled:
            raise
        except Exception as e:
            metadata_complete = False
            logging.warning("Unable to write metadata for %s: %s", path, e)
            Printf.info(f"Downloaded '{title}', but metadata tagging was skipped: {str(e)}")
            if hasattr(userProgress, 'note_warning'):
                userProgress.note_warning(f'Metadata could not be saved for {title}')
        # Verify after tagging too: a failed writer must not leave a corrupt
        # container marked as media-complete.
        media_facts = _verifyMediaQuality(processingPath, stream)
        check_cancelled()
        os.replace(processingPath, path)
        record_completion(
            path,
            audio_identity(stream),
            metadata_complete=metadata_complete,
            media_facts=media_facts,
        )
        # The final media is complete regardless of whether optional metadata
        # succeeded. Its receipt is enough for a tag-only retry.
        _removeFile(partPath)
        _removeFile(partPath + '.source.json')
        Printf.success(title)

        return True, ''
    except DownloadCancelled:
        raise
    except Exception as e:
        # Preserve complete/partial transfer state for resume; only drop empty parts.
        if partPath and _localFileSize(partPath) <= 0:
            _removeFile(partPath)
        _logFailedTrack(track, album, playlist, e)
        Printf.err(f"DL Track '{title}' failed: {str(e)}{_downloadErrorHint(e)}")
        return False, str(e)
    finally:
        if processingPath:
            _removeFile(processingPath)
        destination.close()


def downloadTracks(tracks, album: Album = None, playlist: Playlist = None, progress=None):
    albumCache = {}
    downloadedCovers = set()
    tracks = list(tracks or [])
    total = len(tracks)
    if progress is not None and total:
        progress.begin_collection(total)

    def _getAlbum(item: Track):
        albumId = getattr(getattr(item, 'album', None), 'id', None)
        if albumId is None:
            return None

        if albumId not in albumCache:
            try:
                albumCache[albumId] = TIDAL_API.getAlbum(albumId)
            except DownloadCancelled:
                raise
            except Exception as error:
                logging.warning("Unable to load album %s for playlist track: %s", albumId, error)
                albumCache[albumId] = None

        itemAlbum = albumCache[albumId]
        if SETTINGS.saveCovers and not SETTINGS.usePlaylistFolder and albumId not in downloadedCovers:
            downloadCover(itemAlbum)
            downloadedCovers.add(albumId)
        return itemAlbum

    def _trackProgressKwargs(index):
        if progress is None:
            return {}
        return {"userProgress": progress.for_entry(index + 1) if hasattr(progress, "for_entry") else progress}

    if not SETTINGS.multiThread:
        success = True
        for index, item in enumerate(tracks):
            check_cancelled()
            itemAlbum = album
            if itemAlbum is None:
                itemAlbum = _getAlbum(item)
                item.trackNumberOnPlaylist = index + 1
            if progress is not None:
                progress.begin_entry(index + 1, total, getattr(item, 'title', '') or '')
            check, _ = downloadTrack(item, itemAlbum, playlist, **_trackProgressKwargs(index))
            if progress is not None:
                progress.finish_entry(index + 1, total, check)
                if not check and hasattr(progress, 'note_failed_track'):
                    progress.note_failed_track(item.id)
            success = success and check
        return success
    else:
        futures = {}
        with ThreadPoolExecutor(max_workers=SETTINGS.concurrentTracks) as thread_pool:
            for index, item in enumerate(tracks):
                check_cancelled()
                itemAlbum = album
                if itemAlbum is None:
                    itemAlbum = _getAlbum(item)
                    item.trackNumberOnPlaylist = index + 1
                if progress is not None:
                    progress.begin_entry(index + 1, total, getattr(item, 'title', '') or '')
                futures[thread_pool.submit(
                    copy_context().run, downloadTrack,
                    item,
                    itemAlbum,
                    playlist,
                    **_trackProgressKwargs(index),
                )] = index

            success = True
            for future in as_completed(futures):
                index = futures[future]
                check, msg = future.result()
                if progress is not None:
                    progress.finish_entry(index + 1, total, check)
                    if not check and hasattr(progress, 'note_failed_track'):
                        progress.note_failed_track(tracks[index].id)
                if not check:
                    success = False
                    logging.error("Track download failed: %s", msg)
            return success


def downloadVideos(videos, album: Album, playlist=None, progress=None):
    videos = list(videos or [])
    total = len(videos)
    if progress is not None and total:
        progress.begin_collection(total)
    success = True
    for index, item in enumerate(videos):
        check_cancelled()
        if progress is not None:
            progress.begin_entry(index + 1, total, getattr(item, 'title', '') or '')
        kwargs = {}
        if progress is not None:
            kwargs["userProgress"] = progress.for_entry(index + 1) if hasattr(progress, "for_entry") else progress
        check, _ = downloadVideo(item, album, playlist, **kwargs)
        if progress is not None:
            progress.finish_entry(index + 1, total, check)
            if not check and hasattr(progress, 'note_failed_video'):
                progress.note_failed_video(item.id, getattr(album, 'id', None))
        success = success and check
    return success
