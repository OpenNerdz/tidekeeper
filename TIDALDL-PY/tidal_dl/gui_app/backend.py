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


@dataclass
class AuthStatus:
    user_id: Optional[str]
    country_code: Optional[str]
    expires_after: float
    has_token: bool
    # True only after this poll completed a new device-login grant.
    # Existing saved tokens must not count as "login complete".
    fresh_login: bool = False

    @property
    def label(self) -> str:
        if not self.has_token:
            return "Signed out"
        if self.user_id:
            return f"Signed in as {self.user_id}"
        return "Token saved"

    @property
    def expires_label(self) -> str:
        if not self.expires_after:
            return "Unknown"
        seconds = int(self.expires_after - time.time())
        if seconds <= 0:
            return "Expired"
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        if hours:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"


@dataclass
class AuthChallenge:
    url: str
    user_code: str
    expires_in: int
    interval: int


@dataclass
class SearchItem:
    kind: Type
    title: str
    artists: str
    quality: str
    identifier: str
    duration: str
    source: object
    video_only: bool = False
    status: str = "Queued"
    progress_percent: int = 0
    progress_label: str = ""


class _CallbackWriter(io.TextIOBase):
    def __init__(self, callback: Callable[[str], None]):
        self._callback = callback

    def writable(self):
        return True

    def write(self, text):
        if text:
            self._callback(str(text))
        return len(text)


def _duration_label(seconds) -> str:
    try:
        seconds = int(seconds or 0)
    except (TypeError, ValueError):
        return ""
    if seconds <= 0:
        return ""
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _artists_label(item) -> str:
    artists = getattr(item, "artists", None)
    if isinstance(artists, Iterable) and not isinstance(artists, (str, bytes)):
        names = [getattr(artist, "name", "") for artist in artists]
        return ", ".join(name for name in names if name)
    artist = getattr(item, "artist", None)
    return getattr(artist, "name", "") or ""


def _item_title(item) -> str:
    return getattr(item, "title", None) or getattr(item, "name", None) or "Untitled"


def _item_quality(item, kind: Type | None = None) -> str:
    """Catalog quality plus Atmos/Master/Explicit flags when present.

    Atmos releases often report audioQuality=LOW. Without the audioModes flag
    they look worse than stereo LOSSLESS results even though they are the only
    IDs that can download Dolby Atmos.
    """
    quality = getattr(item, "audioQuality", None) or getattr(item, "quality", None) or ""
    flag = ""
    if kind in (Type.Album, Type.Track, Type.Video):
        try:
            flag = TIDAL_API.getFlag(item, kind, short=False, separator=" · ")
        except Exception:
            flag = ""
    if quality and flag:
        return f"{quality} · {flag}"
    return str(quality or flag or "")


def _item_identifier(item, kind: Type) -> str:
    if kind == Type.Playlist:
        return str(getattr(item, "uuid", "") or "")
    return str(getattr(item, "id", "") or "")


def to_search_item(kind: Type, item) -> SearchItem:
    return SearchItem(
        kind=kind,
        title=_item_title(item),
        artists=_artists_label(item),
        quality=_item_quality(item, kind),
        identifier=_item_identifier(item, kind),
        duration=_duration_label(getattr(item, "duration", 0)),
        source=item,
    )


def with_video_only(item: SearchItem, video_only: bool) -> SearchItem:
    return replace(item, video_only=video_only)


def parse_direct_inputs(text: str, _seen_files: Optional[set] = None) -> List[str]:
    """Split pasted URLs/IDs into one token per queue row.

    Accepts newlines, commas, and space-separated http(s) URLs. A path to an
    existing text file is expanded using the same comment-skipping rules as
    CLI ``start_file``.
    """
    if text is None:
        return []
    stripped = str(text).strip()
    if not stripped:
        return []

    seen_files = set() if _seen_files is None else _seen_files
    if os.path.isfile(stripped):
        path = os.path.abspath(stripped)
        if path in seen_files:
            return []
        seen_files.add(path)
        try:
            with open(stripped, "r", encoding="utf-8") as handle:
                stripped = handle.read()
        except OSError:
            return [stripped]
        if not stripped.strip():
            return []

    tokens: List[str] = []
    seen = set()

    def _add(token: str):
        token = token.strip()
        if not token or token in seen:
            return
        if os.path.isfile(token):
            for nested in parse_direct_inputs(token, seen_files):
                if nested not in seen:
                    seen.add(nested)
                    tokens.append(nested)
            return
        seen.add(token)
        tokens.append(token)

    for line in stripped.splitlines():
        line = line.strip()
        if not line or line[0] in "#[{":
            continue
        if os.path.isfile(line):
            _add(line)
            continue
        for part in line.split(","):
            part = part.strip()
            if not part:
                continue
            if "://" in part and " " in part:
                for piece in part.split():
                    _add(piece)
            else:
                _add(part)
    return tokens


def format_byte_size(num) -> str:
    try:
        value = float(num)
    except (TypeError, ValueError):
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(value) < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} TB"


def format_duration_short(seconds) -> str:
    try:
        total = int(round(float(seconds)))
    except (TypeError, ValueError):
        return ""
    if total < 0:
        return ""
    if total < 60:
        return f"{total}s"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m {secs}s" if secs else f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def format_queue_progress(snapshot: dict) -> str:
    snapshot = snapshot or {}
    count = int(snapshot.get("count") or 0)
    current = int(snapshot.get("current") or 0)
    completed = int(snapshot.get("completed") or 0)
    bytes_current = int(snapshot.get("bytes") or 0)
    bytes_total = int(snapshot.get("bytes_total") or 0)
    speed = float(snapshot.get("speed") or 0)
    eta = snapshot.get("eta")

    parts = []
    if count > 1:
        shown = current if current else min(completed + 1, count)
        parts.append(f"{shown}/{count}")
    elif bytes_total > 0:
        parts.append(f"{format_byte_size(bytes_current)}/{format_byte_size(bytes_total)}")
    if speed > 0:
        parts.append(f"{format_byte_size(speed)}/s")
    if eta is not None:
        label = format_duration_short(eta)
        if label:
            parts.append(label)
    return " · ".join(parts)


def queue_progress_percent(snapshot: dict) -> int:
    snapshot = snapshot or {}
    count = int(snapshot.get("count") or 0)
    completed = int(snapshot.get("completed") or 0)
    bytes_current = int(snapshot.get("bytes") or 0)
    bytes_total = int(snapshot.get("bytes_total") or 0)
    file_frac = (bytes_current / bytes_total) if bytes_total > 0 else 0.0
    if count > 1:
        value = ((completed + file_frac) / count) * 100.0
    elif bytes_total > 0:
        value = file_frac * 100.0
    else:
        return 0
    return int(max(0, min(100, value)))


class TidekeeperBackend:
    def initialize(self):
        SETTINGS.read(PATHS.getProfilePath())
        TOKEN.read(PATHS.getTokenPath())
        if not apiKey.isItemValid(SETTINGS.apiKeyIndex):
            SETTINGS.apiKeyIndex = apiKey.getDefaultIndex()
            SETTINGS.save()
        TIDAL_API.apiKey = apiKey.getItem(SETTINGS.apiKeyIndex)
        self._sync_api_login_key_from_token()

    def _sync_api_login_key_from_token(self):
        TIDAL_API.key.userId = TOKEN.userid
        TIDAL_API.key.countryCode = TOKEN.countryCode
        TIDAL_API.key.accessToken = TOKEN.accessToken
        TIDAL_API.key.refreshToken = TOKEN.refreshToken

    def _save_api_login_key_to_token(self, expires_after: float | None = None):
        TOKEN.userid = TIDAL_API.key.userId
        TOKEN.countryCode = TIDAL_API.key.countryCode
        TOKEN.accessToken = TIDAL_API.key.accessToken
        TOKEN.refreshToken = TIDAL_API.key.refreshToken
        if expires_after is not None:
            TOKEN.expiresAfter = expires_after
        TOKEN.save()

    def _ensure_catalog_session(self):
        self._sync_api_login_key_from_token()
        if aigpy.string.isNull(TOKEN.accessToken):
            raise RuntimeError("Sign in before searching or downloading.")

        if TOKEN.expiresAfter and TOKEN.expiresAfter <= time.time() + 60:
            if loginByConfig():
                self._sync_api_login_key_from_token()
            else:
                raise RuntimeError("Saved login expired. Sign in again from the Account page.")

        if not aigpy.string.isNull(TIDAL_API.key.countryCode):
            return

        try:
            TIDAL_API.loginByAccessToken(TOKEN.accessToken, TOKEN.userid)
            self._save_api_login_key_to_token()
        except Exception:
            if not aigpy.string.isNull(TOKEN.refreshToken) and TIDAL_API.refreshAccessToken(TOKEN.refreshToken):
                self._save_api_login_key_to_token(time.time() + int(TIDAL_API.key.expiresIn))

        self._sync_api_login_key_from_token()
        if aigpy.string.isNull(TIDAL_API.key.countryCode):
            raise RuntimeError("Saved login is missing country data. Refresh saved login or sign in again from Account.")

    def auth_status(self) -> AuthStatus:
        return AuthStatus(
            user_id=TOKEN.userid,
            country_code=TOKEN.countryCode,
            expires_after=TOKEN.expiresAfter or 0,
            has_token=not aigpy.string.isNull(TOKEN.accessToken),
        )

    def refresh_saved_login(self) -> AuthStatus:
        loginByConfig()
        self._sync_api_login_key_from_token()
        return self.auth_status()

    def start_device_login(self) -> AuthChallenge:
        url = TIDAL_API.getDeviceCode()
        return AuthChallenge(
            url=url,
            user_code=TIDAL_API.key.userCode,
            expires_in=int(TIDAL_API.key.authCheckTimeout),
            interval=int(TIDAL_API.key.authCheckInterval),
        )

    def poll_device_login(self) -> AuthStatus:
        if not TIDAL_API.checkAuthStatus():
            return replace(self.auth_status(), fresh_login=False)

        self._save_api_login_key_to_token(time.time() + int(TIDAL_API.key.expiresIn))
        return replace(self.auth_status(), fresh_login=True)

    def logout(self) -> AuthStatus:
        logout()
        return self.auth_status()

    def search(self, text: str, kind: Type) -> List[SearchItem]:
        text = text.strip()
        if not text:
            return []

        if os.path.exists(text):
            return [self.direct_item(text)]

        self._ensure_catalog_session()
        if text.startswith("http"):
            parsed_kind, item_id = TIDAL_API.parseUrl(text)
            if parsed_kind == Type.Null:
                return [self.direct_item(text)]
            item = TIDAL_API.getTypeData(item_id, parsed_kind)
            return [to_search_item(parsed_kind, item)] if item else []

        if kind == Type.Album:
            raw_items = TIDAL_API.searchAlbumsForQuery(text, includeEP=SETTINGS.includeEP)
            return [to_search_item(Type.Album, item) for item in raw_items]

        result = TIDAL_API.searchAll(text, kind)
        if kind == Type.Null:
            items = []
            artists = TIDAL_API.getSearchResultItems(result, Type.Artist)
            for result_kind in (Type.Artist, Type.Album, Type.Track, Type.Playlist, Type.Video):
                raw_items = TIDAL_API.getSearchResultItems(result, result_kind)
                if result_kind == Type.Album:
                    raw_items = TIDAL_API.mergeMatchingArtistAlbums(
                        text,
                        raw_items,
                        artists,
                        includeEP=SETTINGS.includeEP,
                    )
                    raw_items = TIDAL_API.preferAtmosSearchAlbums(raw_items)
                items.extend(to_search_item(result_kind, item) for item in raw_items)
            return items
        raw_items = TIDAL_API.getSearchResultItems(result, kind)
        return [to_search_item(kind, item) for item in raw_items]

    def artist_tracks(self, artist: SearchItem) -> List[SearchItem]:
        self._ensure_catalog_session()
        artist_id = getattr(artist.source, "id", None) or artist.identifier
        if artist_id is None or str(artist_id).strip() == "":
            raise RuntimeError("Artist ID is missing.")

        albums = TIDAL_API.getArtistAlbums(artist_id, includeEP=SETTINGS.includeEP)
        seen_albums = set()
        seen_tracks = set()
        tracks = []
        for album in albums:
            album_id = getattr(album, "id", None)
            if album_id is None or str(album_id).strip() == "" or album_id in seen_albums:
                continue
            seen_albums.add(album_id)
            album_tracks, _ = TIDAL_API.getItems(album_id, Type.Album)
            for track in album_tracks:
                track_id = getattr(track, "id", None)
                if track_id is None or str(track_id).strip() == "" or track_id in seen_tracks:
                    continue
                seen_tracks.add(track_id)
                tracks.append(to_search_item(Type.Track, track))
        return tracks

    def artist_videos(self, artist: SearchItem) -> List[SearchItem]:
        self._ensure_catalog_session()
        artist_id = getattr(artist.source, "id", None) or artist.identifier
        if artist_id is None or str(artist_id).strip() == "":
            raise RuntimeError("Artist ID is missing.")

        seen_videos = set()
        videos = []
        for video in TIDAL_API.getArtistVideos(artist_id):
            video_id = getattr(video, "id", None)
            if video_id is None or str(video_id).strip() == "" or video_id in seen_videos:
                continue
            seen_videos.add(video_id)
            videos.append(to_search_item(Type.Video, video))
        return videos

    def direct_item(self, text: str) -> SearchItem:
        label = os.path.basename(text) if os.path.exists(text) else text
        return SearchItem(Type.Null, label, "", "Direct", text, "", text)

    def download(self, item: SearchItem, log: LogCallback = None, progress=None):
        self._ensure_catalog_session()
        callback = log or (lambda text: None)
        writer = _CallbackWriter(callback)
        kwargs = {}
        if progress is not None:
            kwargs["progress"] = progress
        with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
            if item.kind == Type.Null:
                ok = start(str(item.source), item.video_only, **kwargs)
            else:
                ok = start_type(item.kind, item.source, item.video_only, **kwargs)
        if not ok:
            raise RuntimeError(f"Download failed for {item.title}")

    def apply_runtime_settings(self, values: dict):
        """Apply quality/download options in memory without saving or logout."""
        return self._apply_settings_values(values, persist=False)

    def save_settings(self, values: dict):
        return self._apply_settings_values(values, persist=True)

    def _apply_settings_values(self, values: dict, persist: bool):
        audio_priority = SETTINGS.getAudioQualityPriority(values.get("audioQualityPriority", []))
        previous_api_key_index = SETTINGS.apiKeyIndex
        download_path = str(values.get("downloadPath") or "").strip()
        if not download_path:
            download_path = SETTINGS.downloadPath or "./download/"
        SETTINGS.downloadPath = download_path
        SETTINGS.audioQuality = audio_priority[0] if audio_priority else AudioQuality[values["audioQuality"]]
        SETTINGS.audioQualityPriority = audio_priority
        SETTINGS.videoQuality = VideoQuality[values["videoQuality"]]
        SETTINGS.checkExist = values["checkExist"]
        SETTINGS.includeEP = values["includeEP"]
        SETTINGS.saveCovers = values["saveCovers"]
        SETTINGS.lyricFile = values["lyricFile"]
        SETTINGS.saveAlbumInfo = values["saveAlbumInfo"]
        SETTINGS.downloadVideos = values["downloadVideos"]
        SETTINGS.multiThread = values["multiThread"]
        SETTINGS.downloadDelay = values["downloadDelay"]
        SETTINGS.requestIntervalSeconds = max(0.0, float(values.get("requestIntervalSeconds", 1.0) or 0.0))
        SETTINGS.adaptiveRateLimit = values.get("adaptiveRateLimit", True)
        SETTINGS.saveAsFlac = values.get("saveAsFlac", False)
        SETTINGS.usePlaylistFolder = values["usePlaylistFolder"]
        SETTINGS.showProgress = values["showProgress"]
        SETTINGS.showTrackInfo = values["showTrackInfo"]
        SETTINGS.albumFolderFormat = values["albumFolderFormat"]
        SETTINGS.playlistFolderFormat = values["playlistFolderFormat"]
        SETTINGS.trackFileFormat = values["trackFileFormat"]
        SETTINGS.videoFileFormat = values["videoFileFormat"]
        if persist:
            SETTINGS.language = values["language"]
            SETTINGS.apiKeyIndex = values["apiKeyIndex"]
            TIDAL_API.apiKey = apiKey.getItem(SETTINGS.apiKeyIndex)
            LANG.setLang(SETTINGS.language)
            SETTINGS.save()
        syncPlaybackRateLimiter()
        if persist and SETTINGS.apiKeyIndex != previous_api_key_index:
            # Tokens are bound to the client id. Applying a new key to an old
            # token produces 4022 errors on the next search/download.
            logout()
            TIDAL_API.apiKey = apiKey.getItem(SETTINGS.apiKeyIndex)
            return {"reauth_required": True}
        return {"reauth_required": False}

    def open_download_folder(self, path: str = "") -> str:
        return openPath(path or SETTINGS.downloadPath)

    def api_clients(self):
        return [
            {
                "index": index,
                "platform": item.get("platform", ""),
                "formats": item.get("formats", ""),
                "valid": item.get("valid") == "True",
            }
            for index, item in enumerate(apiKey.getItems())
        ]

    def language_choices(self):
        choices = []
        index = 0
        while True:
            name = LANG.getLangName(index)
            if name == "":
                break
            choices.append((index, name))
            index += 1
        return choices

    def login_by_access_token(self, access_token: str, refresh_token: str = "") -> AuthStatus:
        access_token = access_token.strip()
        if not access_token:
            raise ValueError("Access token is required.")

        TIDAL_API.loginByAccessToken(access_token, TOKEN.userid)
        TOKEN.accessToken = access_token
        TOKEN.refreshToken = refresh_token.strip() or TOKEN.refreshToken
        TOKEN.expiresAfter = 0
        self._save_api_login_key_to_token(TOKEN.expiresAfter)
        return self.auth_status()

    def run_doctor(self) -> str:
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            runDoctor()
        return output.getvalue()

    def update_app(self, include_gui: bool = True) -> str:
        result = run_update(include_gui)
        output = result.output.strip()
        lines = []
        if result.command:
            lines.append("Command: " + " ".join(result.command))
        if output:
            lines.append(output)
        lines.append(result.message)
        if not result.ok and not result.standalone:
            raise RuntimeError("\n".join(lines))
        return "\n".join(lines)

    def version(self) -> str:
        return VERSION


class DemoBackend(TidekeeperBackend):
    def initialize(self):
        SETTINGS.downloadPath = "/Music/Tidekeeper"
        from ..settings import getDefaultAudioQualityPriority

        SETTINGS.audioQuality = AudioQuality.Max
        SETTINGS.audioQualityPriority = getDefaultAudioQualityPriority()
        SETTINGS.videoQuality = VideoQuality.P1080
        SETTINGS.checkExist = True
        SETTINGS.includeEP = True
        SETTINGS.saveCovers = True
        SETTINGS.lyricFile = True
        SETTINGS.saveAlbumInfo = False
        SETTINGS.downloadVideos = False
        SETTINGS.multiThread = False
        SETTINGS.downloadDelay = True
        SETTINGS.requestIntervalSeconds = 3.0
        SETTINGS.adaptiveRateLimit = True
        SETTINGS.saveAsFlac = False
        SETTINGS.usePlaylistFolder = True

    def auth_status(self) -> AuthStatus:
        return AuthStatus("demo-user", "US", time.time() + 7200, True)

    def refresh_saved_login(self) -> AuthStatus:
        return self.auth_status()

    def start_device_login(self) -> AuthChallenge:
        return AuthChallenge("https://login.tidal.com/DEMO-CODE", "DEMO-CODE", 600, 2)

    def poll_device_login(self) -> AuthStatus:
        return replace(self.auth_status(), fresh_login=True)

    def logout(self) -> AuthStatus:
        return AuthStatus(None, None, 0, False)

    def search(self, text: str, kind: Type) -> List[SearchItem]:
        artist = SimpleNamespace(name="The Midnight")
        album = SimpleNamespace(id=101, title="Endless Summer")
        titles = [
            "Sunset",
            "Days of Thunder",
            "Gloria",
            "Los Angeles",
            "Vampires",
            "Jason",
            "Crystalline",
            "Deep Blue",
            "America Online",
            "The Comeback Kid",
            "Synthetic",
            "River of Darkness",
        ]
        qualities = ["HI_RES_LOSSLESS", "LOSSLESS", "HIGH", "LOW"]
        samples = []
        for index in range(72):
            title = titles[index % len(titles)]
            samples.append(
                SimpleNamespace(
                    id=70973230 + index,
                    title=f"{title} {index + 1:02d}",
                    artists=[artist],
                    artist=artist,
                    album=album,
                    duration=220 + (index * 17) % 180,
                    audioQuality=qualities[index % len(qualities)],
                )
            )
        return [to_search_item(kind, item) for item in samples]

    def artist_videos(self, artist: SearchItem) -> List[SearchItem]:
        source_artist = getattr(artist, "source", None)
        if getattr(source_artist, "name", None):
            demo_artist = source_artist
        else:
            demo_artist = SimpleNamespace(id=artist.identifier or 99, name=artist.title or "The Midnight")

        videos = []
        for index, title in enumerate(("Los Angeles", "Sunset", "Vampires", "Deep Blue", "America Online"), 1):
            videos.append(
                SimpleNamespace(
                    id=880000 + index,
                    title=f"{title} video",
                    artists=[demo_artist],
                    artist=demo_artist,
                    album=SimpleNamespace(id=101, title="Video Collection"),
                    duration=180 + index * 15,
                    quality="HIGH",
                    trackNumber=index,
                    releaseDate="2026-01-01",
                    explicit=False,
                )
            )
        return [to_search_item(Type.Video, item) for item in videos]

    def direct_item(self, text: str) -> SearchItem:
        return SearchItem(Type.Null, text, "", "Direct", text, "", text)

    def download(self, item: SearchItem, log: LogCallback = None, progress=None):
        if progress is not None:
            progress.begin_collection(1)
            progress.begin_entry(1, 1, item.title)
            progress.setMaxNum(1)
            progress.addCurNum(1)
            progress.finish_entry(1, 1, True)
        if log:
            log(f"Queued {item.title}\n")
            if item.video_only:
                log("Videos-only mode enabled\n")
            log("Resolved stream metadata\n")
            log("Demo download completed\n")

    def save_settings(self, values: dict):
        audio_priority = SETTINGS.getAudioQualityPriority(values.get("audioQualityPriority", []))
        for key, value in values.items():
            if hasattr(SETTINGS, key):
                setattr(SETTINGS, key, value)
        SETTINGS.audioQualityPriority = audio_priority
        SETTINGS.audioQuality = audio_priority[0] if audio_priority else AudioQuality[values["audioQuality"]]

    def open_download_folder(self, path: str = "") -> str:
        return path or SETTINGS.downloadPath

    def api_clients(self):
        return [
            {"index": 4, "platform": "Tidekeeper OAuth", "formats": "Normal/High/HiFi/Master", "valid": True},
            {"index": 1, "platform": "Fire TV", "formats": "Master-Only", "valid": True},
        ]

    def language_choices(self):
        return [(0, "English"), (13, "French"), (14, "German"), (18, "Japanese")]

    def login_by_access_token(self, access_token: str, refresh_token: str = "") -> AuthStatus:
        return self.auth_status()

    def run_doctor(self) -> str:
        return (
            "Tidekeeper doctor\n"
            "[OK] Download path - /Music/Tidekeeper\n"
            "[OK] TIDAL client - Tidekeeper OAuth\n"
            "[OK] ffmpeg - /usr/bin/ffmpeg\n"
            "[OK] Token - valid for country US\n"
            "[SUCCESS] Doctor finished.\n"
        )

    def update_app(self, include_gui: bool = True) -> str:
        target = "terminal and GUI" if include_gui else "terminal"
        return f"Demo update completed for {target} install. Restart Tidekeeper to use the updated version."
