# Changelog

## Unreleased

- Fixed downloads labeled FLAC saving with .m4a extension: now use .flac for FLAC codec (with optional ffmpeg remux from containerized DASH segments to produce valid standalone FLAC files; falls back gracefully).
- Fixed GUI elements (menus, track lists, sections) invisible or white/blank on Windows 11 dark theme by forcing Fusion style + explicit light QPalette + expanded stylesheet rules.
- Added configurable request delay interval (downloadDelaySec) to manually set seconds between audio stream requests, helping avoid Tidal rate limiting (CLI prompt, GUI spinbox, settings, dynamic rate limiter).
- Improved vague "can't download" cases with better error hints in output (quality, network, permission, disk), Windows-specific doctor advice, and more actionable messages.
- Updated tests, paths logic, GUI, CLI, backend, diagnostics, and docs accordingly.
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
