# Changelog

## Unreleased

- Fixed `-l`/`--link` downloads so the CLI exits when finished instead of dropping into the interactive menu (#39, thanks @redraven2459).
- Fixed album artist metadata conversion so album artist lists and `{ArtistName}`/`{ArtistID}` album tokens are populated correctly (#38, #41).
- Reduced HTTP 429 rate-limit errors by pacing playback manifest requests and caching duplicate stream manifest lookups.
- Added a `--configPathOverride` CLI argument for custom config locations (#37, thanks @redraven2459).
- Added the `{AlbumArtistID}` album path token (#36, thanks @redraven2459).
- GUI now reports failed queue items as Failed instead of Done when downloads return errors.
- CLI `-l`/`--link` exits with a non-zero status when downloads fail.
- Lookup errors (401/403/network) are no longer masked as "No result." while probing media types.
- Hardened path tokens, artist lists, and empty search results against missing/null API fields.
- Shortened stream-manifest cache TTL so expired CDN URLs are less likely to be reused.
- Exposed adaptive rate-limit toggle in GUI settings layout and CLI settings.

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
