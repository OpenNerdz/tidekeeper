# Changelog

## Unreleased

- `{ArtistID}` in video file formats now lists every video artist ID (matching `{Artists}` behavior) and skips artists without an ID instead of rendering `None`.
- Deduplicated download progress helpers: removed `__addExistingProgress__` (identical to `__noteProgress__`) and repointed resume/reuse call sites, fixing a potential `NameError` on resumed downloads.
- Code hygiene: replaced `== None` / `== False` comparisons with `is None` / `not ...` (`paths.py`, `printf.py`, `__init__.py`).
- Reduced TIDAL API rate-limit pressure without changing successful download quality:
  - OpenAPI no longer retries DOWNLOAD→PLAYBACK after permanent `CLIENT_NOT_ENTITLED` blocks (was 2 limited calls for Atmos misses).
  - Atmos quality no longer probes standard playback as accidental `HI_RES`; fall through uses the configured quality priority instead.
  - Session caches for Atmos twin albums/tracks and Atmos-unavailable track IDs.
  - Catalog HTTP 429s apply the same adaptive backoff as playback/manifest requests.
  - Catalog calls only join the request delay while adaptive backoff is elevated after a 429.
  - Stream manifest resolution is single-flight across multi-thread downloads.

## 2026.8.4.0 - 2026-08-04

### Dolby Atmos catalog selection (#44)

- Search quality labels show `Dolby Atmos` when `audioModes` includes `DOLBY_ATMOS` (Atmos releases often report `LOW`).
- Album search injects matching Atmos catalog twins when TIDAL only returns the stereo row.
- Track models retain `audioModes` from TIDAL search/catalog payloads.
- When download quality is Atmos, stereo album/track/playlist/mix picks auto-resolve to the matching Atmos catalog twin (no Android URL required).
- Artist downloads skip stereo albums when an Atmos twin is already in the list.
- GUI applies current Settings (including Atmos quality) before starting downloads.
- Album details print max quality, audio modes, and flags.

### Packaging and reliability

- Documented and enabled first-party PyPI installs (`pip install tidekeeper`).
- `tidekeeper --update` and the one-line installer now install from PyPI by default.
- Hardened track CDN downloads for reliability and stability:
  - Mismatched HTTP Range responses re-fetch fully instead of writing a truncated body.
  - Multi-segment DASH/HLS parts use per-segment resume (sequential and parallel).
  - Stable `.parts` directories keep finished segments across retries; fail-fast cancels sibling segment jobs.
  - Post-download size verification against Content-Length / Content-Range totals.
  - HEAD size probes fall back to a 1-byte ranged GET when CDNs reject HEAD.
  - Complete assembled `.part` files are reused after decrypt failures (no redundant CDN re-fetch).
  - Parallel segment workers share the resumable single-URL path with thread-safe progress.

## 2026.7.30.0 - 2026-07-30

### Reliability and correctness

- Fixed `-l`/`--link` downloads so the CLI exits when finished instead of dropping into the interactive menu (#39, thanks @redraven2459).
- CLI `-l`/`--link` exits with a non-zero status when downloads fail.
- Fixed `--doctor`, `--gui`, module execution, and standalone builds returning success after operational failures.
- Invalid config paths and updater launch failures now produce clean errors instead of tracebacks.
- GUI now reports failed queue items as Failed instead of Done when downloads return errors.
- Lookup errors (401/403/network) are no longer masked as "No result." while probing media types.
- Reduced HTTP 429 rate-limit errors by pacing playback manifest requests and caching duplicate stream manifest lookups.
- Shortened stream-manifest cache TTL so expired CDN URLs are less likely to be reused.

### Metadata and path tokens

- Fixed album artist metadata conversion so album artist lists and `{ArtistName}`/`{ArtistID}` album tokens are populated correctly (#38, #41).
- Fixed track/album tagging and path building when TIDAL omits the artist list, which previously raised `'NoneType' object is not iterable` (follow-up to #38).
- Hardened path tokens, artist lists, and empty search results against missing/null API fields.
- Fixed `{ArtistID}`/`{AlbumArtistID}` album path tokens writing literal `None` when TIDAL omits an artist ID; those artists are now skipped.
- Fixed `{AlbumArtistID}` and `{AlbumArtistName}` rendering literal `None` when primary artist fields are absent.
- Added the `{AlbumArtistID}` album path token (#36, thanks @redraven2459).
- Added a `--configPathOverride` CLI argument for custom config locations (#37, thanks @redraven2459).

### Packaging, Docker, and release tooling

- Added a release workflow that builds the sdist and wheel and publishes to PyPI with trusted publishing.
- Added a Dockerfile that bundles ffmpeg and keeps config, tokens, and logs in `/config` with downloads in `/downloads`.
- Added Python 3.14 to the CI matrix and a packaging job that verifies the PyPI long description survives the sdist round trip.
- Fixed the local build script deleting packaging metadata and omitting the GUI executable.
- Aligned runtime dependency pins between `setup.py` and `requirements.txt`.
- Added a high-signal Ruff lint gate in CI (syntax and undefined-name defects).
- Documented container usage, ffmpeg recommendation, and the complete GitHub/PyPI release checklist.

### Contributor experience

- Fixed the test suite reading and overwriting the real `~/.tidal-dl.json` profile, which caused false rate-limit test failures for contributors.
- Exposed adaptive rate-limit toggle in GUI settings layout and CLI settings.
- Replaced deprecated PrettyTable `PLAIN_COLUMNS` usage with `TableStyle`.

## 2026.7.11.0 - 2026-07-11

- Improved lossless and hi-res fallback behavior, request pacing, and handling of HTTP 403/429 responses.
- Added `{ArtistID}` support for album folder formats.
- Added Python 3.10–3.13 CI coverage, dependency automation, and updated build actions.
- Improved Termux installation guidance and dependency handling.
- Added regression coverage and maintenance cleanup; the full suite now contains 109 tests.
- Streamlined project documentation and repository contribution metadata.

## 2026.6.2.0 - 2026-06-02

- Fixed the desktop GUI on Windows 11 dark mode so menus, search results, and settings are readable instead of blank or all white.
- Added an optional **Save FLAC as .flac files** setting (GUI and CLI); uses ffmpeg when available and keeps `.m4a` if conversion is not possible.
- Added a configurable **request interval** between TIDAL playback requests (GUI and CLI) to help with rate limiting.
- Improved download handling when TIDAL says a track is not ready yet, with automatic retries and clearer error hints.
- Added video-only artist downloads in the terminal and desktop GUI.
- Improved download reliability with resumable single-file downloads, safer final-file replacement, pooled HTTP sessions, token refresh retry on expired API calls, and reduced duplicate album/cover lookups.
- Added a README GUI gallery with Search, Queue, Settings, and Account screenshots.
- Added in-app update actions for the terminal workflow and desktop GUI.
- Added `--paths`, `--open-output`, and a GUI download-folder open action for quicker access to files and config locations.
- Added a GUI fallback-order preset selector for audio quality priority.
- Reorganized GUI pages into clearer workflow sections for faster scanning.
- Improved GUI action states so unavailable search, direct download, and queue actions are disabled until usable.
- Improved GUI account maintenance layout and guarded against duplicate background actions.
- Fixed sorted GUI tables so selected search and queue rows resolve the intended item.

## 2026.5.23.0 - 2026-05-23

- Fall back through lower audio qualities when a requested stream manifest is blocked or unavailable, and show the fallback in track output.
- Added `tidekeeper --doctor` to check config, token status, download path access, and local tools.
- Added the modern PySide6 desktop GUI with feature parity for terminal auth, search, queue, direct downloads, settings, client selection, token login, and doctor diagnostics.
- Added automated GUI screenshot smoke testing with dense demo data for layout validation.
- Added cross-platform GUI executable builds and release uploads for Windows, Linux, and macOS.

## 2026.5.17.4 - 2026-05-18

- Added `SECURITY.md`, `CONTRIBUTING.md`, and release changelog docs.
- Linked project governance docs from the README.
- Restricted local token file permissions to owner-only on POSIX systems.
- Improved parsing for TIDAL share URLs with query strings, fragments, and nested paths.
- Added regression coverage for URL parsing and token file permissions.

## 2026.5.17.3 - 2026-05-18

- Added Dolby Atmos stream support and Atmos filename identification.
- Added `failed-tracks.txt` logging for failed track downloads.
- Improved Termux install and first-run behavior.
- Added the one-command Linux/Termux installer.
- Fixed the lyrics endpoint.
- Hardened terminal auth and path handling.
- Refreshed README branding and repository maintenance files.

## 2026.5.16.7 - 2026-05-16

- Fixed executable workflow dependencies.
