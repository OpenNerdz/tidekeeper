#!/usr/bin/env python3
"""Live integration check for GitHub issue #18 rate-limit / manifest paths."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tidal_dl import events
from tidal_dl.download import downloadTrack
from tidal_dl.enums import AudioQuality
from tidal_dl.paths import getProfilePath, getTokenPath
from tidal_dl.settings import SETTINGS, TOKEN
from tidal_dl.tidal import TIDAL_API

# From GitHub issue #18 (supxr artist bulk download; track IDs resolved via TIDAL API)
ISSUE_TRACKS = [
    (408232199, "TELL ME!"),
    (403499912, "IN MY HEAD!"),
    (401143931, "SWINDLE"),
    (401143932, "NEXT"),
    (401143933, "YOUR LOSS"),
    (396529624, "GRAY"),
    (391522404, "CRUSH"),
    (388279201, "OTHER HALF"),
    (448263217, "HEARTS"),
    (366303431, "WHATS UP!"),
    (321133875, "PRONE"),
    (320049464, "CONFESS"),
    (318803857, "GLAZ"),
]


def main():
    SETTINGS.read(getProfilePath())
    TOKEN.read(getTokenPath())
    SETTINGS.downloadDelay = True
    SETTINGS.requestIntervalSeconds = 5
    SETTINGS.multiThread = False
    SETTINGS.checkExist = False
    SETTINGS.showProgress = False
    SETTINGS.showTrackInfo = True
    SETTINGS.audioQuality = AudioQuality.HiFi
    SETTINGS.audioQualityPriority = [
        AudioQuality.HiFi,
        AudioQuality.Max,
        AudioQuality.High,
    ]

    out_dir = os.environ.get(
        "TIDEKEEPER_ISSUE18_TEST_DIR",
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "issue18-live-test"),
    )
    os.makedirs(out_dir, exist_ok=True)
    SETTINGS.downloadPath = out_dir

    if not events.loginByConfig():
        print("FAIL: could not log in (check ~/.tidal-dl.token.json)")
        return 1

    album_cache = {}
    ordered = []
    for track_id, label in ISSUE_TRACKS:
        track = TIDAL_API.getTrack(track_id)
        if track.title.strip().upper() != label.strip().upper():
            print(f"WARN: id {track_id} title {track.title!r} != expected {label!r}")
        ordered.append(track)

    print(f"Artist: supxr (issue #18 track list)")
    print(f"Testing {len(ordered)} tracks -> {out_dir}")
    print("-" * 60)

    results = []
    for index, track in enumerate(ordered, 1):
        print(f"\n[{index}/{len(ordered)}] {track.title} (id={track.id})")
        started = time.time()
        album_id = track.album.id
        if album_id not in album_cache:
            album_cache[album_id] = TIDAL_API.getAlbum(album_id)
        ok, msg = downloadTrack(track, album_cache[album_id])
        elapsed = time.time() - started
        status = "OK" if ok else "FAIL"
        results.append((track.title, track.id, status, msg, elapsed))
        print(f"  -> {status} ({elapsed:.1f}s)")
        if not ok:
            print(f"     {msg}")

    print("\n" + "=" * 60)
    print("SUMMARY")
    ok_count = sum(1 for item in results if item[2] == "OK")
    print(f"Passed: {ok_count}/{len(results)}")
    for title, track_id, status, msg, elapsed in results:
        line = f"  [{status}] {title} ({track_id}) {elapsed:.1f}s"
        if status == "FAIL":
            line += f" — {msg[:120]}"
        print(line)
    return 0 if ok_count == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
