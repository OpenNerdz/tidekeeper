# Changelog

## Unreleased

## 2026.10.7.1 - 2026-10-07

<!-- release-title: No leftover cover files -->

- Stop leaving a `cover.jpg.source.json` file next to each saved album cover.

[Full changes](https://github.com/OpenNerdz/tidekeeper/compare/v2026.10.7.0...v2026.10.7.1)

## 2026.10.7.0 - 2026-10-07

<!-- release-title: Optional download receipts -->

- Add a **Save download receipts** setting to stop writing `.tidekeeper.json`
  files next to downloads. When it is off, skipping only checks that a file
  exists.

[Full changes](https://github.com/OpenNerdz/tidekeeper/compare/v2026.10.3.0...v2026.10.7.0)

## 2026.10.3.0 - 2026-10-03

<!-- release-title: Reliable sign-in and focused queue retries -->

- Keep a newer login safe when requests, token refreshes, or device sign-in from
  an earlier session finish late.
- Keep Download now and Retry incomplete focused on the requested items while
  still accepting jobs added during the download. Preserve failure details when
  a retry cannot start, remove the redundant early queue reset, and sort queue
  progress numerically.
- Validate compressed media responses using decoded file sizes instead of
  compressed transfer sizes, and honor cancellation before replacing a completed
  transfer's destination.
- Display tracks with missing album metadata without interrupting downloads.
- Prepare queued manual releases from the latest main commit and carry that
  source through the checked promotion step.
- Stop the Linux dependency installer when refreshing apt's package index fails,
  and create working launchers when the installation folder is a relative path.

[Full changes](https://github.com/OpenNerdz/tidekeeper/compare/v2026.9.29.4...v2026.10.3.0)

## 2026.9.29.4 - 2026-09-29

<!-- release-title: Reliable containers and fully gated releases -->

- Fall back from an unavailable home/app-state lock folder to private temporary
  storage or the download root, so read-only homes and numeric Docker users can
  download normally.
- Bound local and shared lock files to 256 reusable slots, clean inactive legacy
  per-track locks when an album is revisited, and coordinate separate machines
  through one hidden folder at the shared download root when its filesystem
  supports locking.
- Merge discoverable downloads from the pre-2026.9.29 literal `~` folder without
  replacing conflicts, and add `--migrate-downloads PATH` for any old launch
  directory Tidekeeper cannot discover.
- Accept transparently decoded compressed responses for fresh downloads while
  continuing to reject unsafe encoded byte-range resumes.
- Show the expanded download folder in errors and let remote logout revocation
  finish when the desktop window closes.
- Build releases on an isolated candidate, promote it only after every check and
  platform build passes, and create the version tag only after PyPI verifies both
  distributions. Automated release commits now use `github-actions[bot]`, and
  the resulting tag does not launch a duplicate build.
- Stop scheduled supporter commits to `main`; the desktop still refreshes the
  current stargazer list directly and retains its bundled offline snapshot.

[Full changes](https://github.com/OpenNerdz/tidekeeper/compare/v2026.9.29.3...v2026.9.29.4)

## 2026.9.29.3 - 2026-09-29

<!-- release-title: Cleaner downloads and controlled releases -->

- Keep destination locks in a private per-user state folder rather than hidden
  folders inside download libraries, including network shares. Explain waits for
  another writer after two seconds and keep cancellation responsive.
- Remove repeated desktop quality labels such as "Master · Master" and avoid
  describing an Atmos result as Normal quality.
- Detect downloads saved in a literal `~` folder by older releases and tell the
  user where to move them before Tidekeeper downloads the same media again.
- Document `TIDEKEEPER_DOWNLOAD_PATH` and the new lock locations.
- Make normal pushes full CI/platform-build previews. Publishing now requires the
  Build workflow's manual **publish** switch, and docs, tests, workflows,
  installers, Docker, and release tooling no longer create update prompts alone.
- Read PyPI's package index instead of its cached per-version endpoint when
  verifying uploads, and retry brief network or server failures.
- Refresh the bundled supporter snapshot once daily instead of committing once
  for every new star.

[Full changes](https://github.com/OpenNerdz/tidekeeper/compare/v2026.9.29.2...v2026.9.29.3)

## 2026.9.29.2 - 2026-09-29

<!-- release-title: More reliable publishing -->

- Wait up to six minutes for PyPI to list a new release before publishing it on
  GitHub, instead of failing after 50 seconds while PyPI's cache catches up.

[Full changes](https://github.com/OpenNerdz/tidekeeper/compare/v2026.9.29.1...v2026.9.29.2)

## 2026.9.29.1 - 2026-09-29

<!-- release-title: Rewritten README and guides -->

- Rewrite the README around installing, signing in, and downloading, with a
  complete option table, quality guide, and troubleshooting. Document the default
  filename templates and correct the duration and flag label descriptions.

[Full changes](https://github.com/OpenNerdz/tidekeeper/compare/v2026.9.29.0...v2026.9.29.1)

## 2026.9.29.0 - 2026-09-29

<!-- release-title: Clearer errors and consistent download folders -->

- Expand `~` in the download folder for every album, playlist, video, cover,
  failure log, and doctor check; previously only single tracks honored it and
  other downloads could land in a literal `~` folder.
- Search the catalog when desktop search text matches a local folder name
  (such as `download`); regular files are treated as direct-link lists regardless
  of their filename extension.
- Keep album, playlist, and artist downloads running when TIDAL omits a title.
- Report readable errors such as "Get operation failed: Album not found"
  instead of joined text or stale gateway pages, and only suggest checking disk
  space for real out-of-space errors.
- Show quality as Max, HiFi, High, or Normal in desktop results and the queue,
  describe expired or unknown sessions naturally, confirm settings reloads, and
  give the desktop app its own window and taskbar icon.
- Fall back to English for settings labels missing from a translation, and apply
  terminal concurrency changes only when both values are valid.
- Simplify internal naming, option parsing, and duplicated quality tables; remove
  unused manifest helpers and point-in-time review documents.

[Full changes](https://github.com/OpenNerdz/tidekeeper/compare/v2026.9.28.2...v2026.9.29.0)

## 2026.9.28.2 - 2026-09-28

<!-- release-title: Automated releases and faster builds -->

- Automatically prepare dated releases from application changes on main, retaining
  the existing daily version counter, tag format, and concise release-note style.
  Publish GitHub drafts only after all checks and PyPI hash verification pass;
  resume matching partial uploads without replacing published files.

- Include missing X11 libraries in Linux desktop builds and verify GUI startup
  on a virtual X11 display as part of CI and release checks.

- Refresh GUI supporters on new GitHub stars and scheduled runs, show the bundled
  list immediately, and refresh long-running sessions when Account is reopened.
  Validate generated snapshots and preserve the previous list on API failures.

- Reuse local PyInstaller build work and Docker dependency layers; keep generated
  files out of Git and Docker contexts, and update setup and maintenance guides.

- Run release CI and platform builds in parallel, validate tag/version/changelog
  agreement before building binaries, run CI for manual builds too, and smoke
  test the built wheel outside the source tree before publishing it.

- Cancel superseded branch runs, bound job runtime and artifact retention, cache
  CI tooling/dependencies, and avoid recompressing release artifacts.

- Find and resume unpublished GitHub drafts by release ID, including drafts
  omitted from the public tag endpoint, before verifying and publishing assets.

[Full changes](https://github.com/OpenNerdz/tidekeeper/compare/v2026.9.28.0...v2026.9.28.2)

## 2026.9.28.1 - 2026-09-28

<!-- release-title: Automated releases and faster builds -->

> This version was never published. Its changes shipped in 2026.9.28.2.

- Automatically prepare dated releases from application changes on main, retaining
  the existing daily version counter, tag format, and concise release-note style.
  Publish GitHub drafts only after all checks and PyPI hash verification pass;
  resume matching partial uploads without replacing published files.
- Include missing X11 libraries in Linux desktop builds and verify GUI startup
  on a virtual X11 display as part of CI and release checks.
- Refresh GUI supporters on new GitHub stars and scheduled runs, show the bundled
  list immediately, and refresh long-running sessions when Account is reopened.
  Validate generated snapshots and preserve the previous list on API failures.
- Reuse local PyInstaller build work and Docker dependency layers; keep generated
  files out of Git and Docker contexts, and update setup and maintenance guides.
- Run release CI and platform builds in parallel, validate tag/version/changelog
  agreement before building binaries, run CI for manual builds too, and smoke
  test the built wheel outside the source tree before publishing it.
- Cancel superseded branch runs, bound job runtime and artifact retention, cache
  CI tooling/dependencies, and avoid recompressing release artifacts.

[Full changes](https://github.com/OpenNerdz/tidekeeper/compare/v2026.9.28.0...v2026.9.28.1)

## 2026.9.28.0 - 2026-09-28

- Keep Termux destination lock files on its private filesystem so downloads to
  Android shared storage do not fail with `Errno 38`.
- Publish the already validated wheel and source distribution from release CI
  instead of building the same packages again; avoid a full-history checkout
  and a redundant cleanup on fresh build runners. Manual platform builds use
  the CI result already checked on `main`; release tags still rerun the full gate.
- Keep Python distributions out of standalone release assets and require the
  configured PyPI token in the reusable publishing workflow.
- Keep only `main` as the repository branch.

## 2026.9.26.1 - 2026-09-26

- Restore scheme-less TIDAL links in terminal commands, batch lists, desktop
  Links, and search while retaining exact-host and media-ID validation.
- Cancel device login independently of saved-session work, so searches and token
  refreshes can finish normally. Keep stale device replies from changing login
  state or polling intervals.
- Show a persistent closing message while downloads or background work stop,
  explain when an update must finish, and disable new work while closing.
- Accept immutable HLS playlists marked `VOD` without an end marker, while
  continuing to reject unfinished/live playlists. Exercise the full video
  download/finalization path with generated HLS and real FFmpeg.
- Extend destination locks across Tidekeeper instances with cancellable OS file
  locks. Test competing track/video writers through completion receipts, process
  cancellation, and lock release after a process exits on every build platform.
- Preserve valid partial downloads when a server unexpectedly compresses its
  response. Cover encoding, range, and HTTPS redirect checks with regressions.

## 2026.9.26.0 - 2026-09-26

- Make device login cancellable, ignore stale login replies, honor polling
  backoff, and prevent overlapping account changes and downloads. Clear manual
  token fields after sign-in and wait for background workers when closing.
- Validate terminal options before changing settings, keep help/version free
  of profile writes, hide manual token input, and handle cancellation cleanly.
- Show transfer totals learned from media responses, serialize concurrent
  writes to the same destination, and make connection waits cancellable.
- Correct video resolution selection and root output paths; reject preview
  audio/video, incomplete HLS, and unsupported multi-period DASH instead of
  marking partial content complete. Verify small audio files with ffprobe too.
- Harden remote manifest/artwork reads, URL validation, redirect handling,
  credential redaction, disc-folder names, and media-tool input restrictions.
  Bound batch lists and expanded manifests before they consume excessive memory.
- Pin workflow actions to reviewed commits, reduce build permissions, audit
  terminal/desktop dependencies in CI, and add actual FFmpeg integration tests.

## 2026.9.24.1 - 2026-09-24

- Keep unattempted albums and failed videos in desktop retries after a catalog
  error or when reopening older queues without complete failure details.
- Preserve failed videos' album folders and partial transfers across retries
  and restarts, including videos shared by multiple albums.

## 2026.9.24.0 - 2026-09-24

- Desktop retries of failed artist and album downloads target the failed tracks
  and videos instead of downloading the collection again. Saved queues retain
  those failures across restarts; older failed rows can use matching entries in
  `failed-tracks.txt`.

## 2026.9.23.0 - 2026-09-23

- Write `AlbumInfo.txt` when TIDAL omits an album's volume count, listing every
  track. A failure to write it is now reported without stopping the album
  download.
- Release the console output lock when a message cannot be printed, for
  example when a pipe is closed or the console cannot encode the text. Before
  this fix, all later output from download workers stopped.
- Recognize TIDAL links regardless of hostname case, and keep the current
  terminal language when the language choice is invalid.
- Desktop: drop TIDAL links or `.txt` lists onto the window to add them to
  Links, and disable **Run doctor** until the current check finishes.
- Save login tokens and build OAuth requests in one shared place instead of
  five copies, and remove settings normalization code that could never run.

## 2026.9.20.3 - 2026-09-20

- Reject preview-only OpenAPI manifests and retry the same format through the
  playback usage, preventing short high-resolution previews from being saved
  and reported as complete tracks.
- Keep the selected audio quality ahead of saved fallback entries, including
  older or hand-edited profiles, so choosing Max cannot silently start at HiFi.

## 2026.9.20.2 - 2026-09-20

- Treat numeric DASH representation IDs as identifiers while retaining
  bit-depth detection for FLAC-family IDs, preventing incorrect quality
  selection and false verification failures.
- Reserve filename space for transfer receipts, temporary processing files,
  and FLAC remux output, including long Unicode titles.
- Follow validated redirects when embedding artwork and close rejected redirect
  responses.
- Clear local login state immediately on logout and client changes, and revoke
  desktop sessions in a background worker without affecting a newer login.
- Use the smaller PySide6 Essentials dependency for the desktop, consolidate
  completion checks and path sanitization, and right-size per-thread HTTP pools.
- Remove redundant helpers and archived investigation notes; exclude development
  caches, tests, and generated screenshots from the Docker build context.

## 2026.9.20.1 - 2026-09-20

- Prefer TIDAL's fixed OpenAPI FLAC manifests for HiFi and Max, then use the
  playback API as an independent fallback. Select the highest-fidelity DASH
  representation by codec, bit depth, sample rate, and bandwidth instead of
  trusting response order; expose those facts in the CLI, desktop progress,
  and completion receipt, with optional `ffprobe` verification.
- Let generic v4 playback 404s fall through to unversioned and legacy routes.
  Cache only explicit client-entitlement blocks and expire those capability
  decisions instead of poisoning a quality for the entire process.
- Revoke TIDAL sessions remotely on logout and client changes. Harden remote
  manifests with entity, size, node, private-network URL, credential, and
  redirect checks.
- Repair failed metadata directly on verified media without downloading it
  again. Use fast sampled fingerprints for routine skip checks, retain resume
  state across renewed signed CDN URLs, and keep media-selecting query fields
  in the transfer identity.
- Replace the legacy filename filter with portable Unicode-aware component and
  traversal protection. Separate track and segment concurrency while capping
  all simultaneous media connections.
- Build release binaries only for tags, add distinct Apple Silicon and Intel
  macOS packages, use Ubuntu 22.04 for wider x86-64 compatibility, preserve
  Unix executable modes in archives, and publish SHA-256 checksums plus GitHub
  build-provenance attestations.

## 2026.9.20.0 - 2026-09-20

- Add a current HiRes-capable TIDAL device-flow client and use it for new
  profiles, enabling Max streams up to 24-bit/192 kHz when offered by the track
  and account. Preserve the TV client at its stable index for existing sessions
  and manual fallback.

## 2026.9.17.1 - 2026-09-17

- Fix issue #65's login loop: playback-only HTTP 404/subStatus 4022 no longer
  refreshes or erases a newly authorized session. Alternate manifest requests
  and configured quality fallbacks can run; catalog client rejection still
  clears an unusable session without retrying with an empty bearer token.
- Treat legacy Master (retired MQA) selections as lossless FLAC. A single Master
  selection tries Max then HiFi; explicit fallback orders remain in control,
  and no fallback ladder requests retired MQA.
- Include the playback endpoint, client label, country, and quality in 4022
  diagnostics without tokens or secrets, and stop recommending repeated logout
  for playback-only failures.
- Reject DRM-protected DASH manifests before downloading their segments. Use
  available clear streams within the configured fallback order instead of
  saving encrypted audio and reporting it as a successful download.
- Remove disabled login clients from both selectors without renumbering saved
  client IDs. Keep current sessions and supported legacy profiles compatible.
- Share current quality/fallback choices across playback, CLI and desktop;
  migrate saved Master settings in the desktop and include 240p in the CLI.
- Remove unused helpers and the obsolete issue-18 live script. Consolidate
  terminal help, translated quality prompts, demo choices and dependency pins.

## 2026.9.17.0 - 2026-09-17

- Replace the Android Auto OAuth client, which could authorize a login but produced unusable 4022 sessions,
  with the current TV device-flow client.
- Record the client that issued each saved token and require one clean login when an update changes clients,
  preventing incompatible legacy sessions from reaching the first download.

## 2026.9.15.0 - 2026-09-15

- Replace the retired default TIDAL OAuth client and clear saved sessions that TIDAL rejects with subStatus 4022,
  allowing the next login to establish a genuinely fresh session.

## 2026.9.14.1 - 2026-09-14

- Sort desktop search-result durations by elapsed time instead of their formatted text.

## 2026.9.14.0 - 2026-09-14

- Added a compact, scrollable Supporters section to the desktop Account panel.
  It loads the current GitHub stargazer snapshot off the UI thread, links each
  username to their profile, and retains the bundled list when offline.
- Refresh the supporter snapshot every six hours with an authenticated
  repository workflow, keeping GitHub credentials out of distributed clients.

## 2026.9.12.0 - 2026-09-12

- Stop probing every DASH audio object for its size before downloading. Actual
  transfer responses still verify object sizes, while completed-transfer markers
  record the assembled size for safe retry reuse without extra CDN requests.

## 2026.9.9.1 - 2026-09-09

- Bounded CDN retries at the transfer layer, stopped playback endpoint fallback after rate-limit exhaustion, and made zero/invalid retry delays safe. Shared retry parsing now supports HTTP-date headers.
- Closed catalog, manifest, and artwork responses consistently. Artwork HTTP failures are no longer returned as image data, and size probes no longer mistake a partial response length for the whole file.
- Rejected empty completed transfers and prevented double-counted progress when a server restarts a resumed download.
- Protected active queue items from the Delete shortcut and direct queue-removal actions.
- Read settings and token files consistently as UTF-8, support byte-order marks, and recover from invalid encoding without reusing stale values.
- Replaced wildcard imports with explicit dependencies, removed the obsolete size-only skip helper and unused imports, and expanded lint checks to prevent their return.
- Consolidated queue insertion and prevent duplicate unfinished jobs, including equivalent catalog selections and pasted links. Added undo for removal, Clear done, and retry for partial, cancelled, and interrupted jobs.
- Show persistent, redacted failure details beside selected queue rows, with inline search errors and automatic download-log opening when attention is needed.
- Added cancellable searches, explicit unsaved-settings feedback, and a compact table layout that preserves readable titles beside Settings or Account.
- Restore runtime settings after a failed save before changing the login client. Demo settings now share the real conversion code and preserve enum types when saved and reloaded.
- Build Linux ARM64 terminal and desktop executables in GitHub Actions alongside Windows, macOS, and Linux x86-64 releases.

## 2026.9.9.0 - 2026-09-09

- Fixed Termux installation attempting to replace system pip, Arch partial upgrades, and the download-folder environment override being ignored outside Termux (including Docker).
- Diagnostics use a temporary file without overwriting an existing write-test file.
- CLI and GUI share a batch parser with cycle detection, relative nested lists, BOM support, whitespace-separated IDs, and duplicate removal. CLI batches continue after individual lookup failures.
- Reload reads saved settings from disk. Missing or damaged profiles clear old state, and manual login no longer reuses an unrelated refresh token.
- Cancelled assembly and FLAC remux clean up their temporary output while retaining retry data. Catalog pagination avoids an unnecessary request after a full final page.
- Desktop logs use bounded plain text and preserve scroll position. Queue summaries distinguish partial, cancelled, and interrupted items; retries clear stale progress and quality.
- Queue columns leave more room for titles and can be resized; cells expose complete text in tooltips. Form fields have accessible labels, and empty searches explain that no matches were found.
- Added regression coverage, restored settings isolation between tests, and smoke-test packaged terminal executables during platform builds.
- Verified all 302 tests with Qt enabled under Ubuntu proot. Screenshot generation now uses the real application theme; refreshed the desktop documentation screenshots.

## 2026.9.7.0 - 2026-09-07

### Reliability

- Retrying a partial download repairs failed metadata instead of skipping the file and incorrectly reporting success. Completed transfer data is retained for the retry.
- Parallel media-size probes inherit cancellation state and cancel pending probes, so cancellation no longer leaves the full probe queue running.

## 2026.9.5.0 - 2026-09-05

### Reliability

- Failed stream replacements cannot cause retries to reuse an old file of the same size.

- Interrupted downloads no longer mix segments from a different stream, and completed files are skipped only with a matching checksum receipt.
- Truncated FLACs, failed video remuxes, and videos that ignore “Skip existing files” are no longer treated as successful.
- A finished `.download` sidecar that gets HTTP 416 is promoted instead of failing the retry.
- Fresh settings keep 720p, invalid numeric settings no longer crash startup, and `--configPathOverride=/path` is recognized.
- Token verification treats HTTP failures as errors instead of a valid login, and logout cancels in-flight device login and session caches.
- HLS/DASH parsers resolve relative segment URLs and inherited DASH timelines.

### GUI

- Queue rows are independent of search results, restore as Interrupted after restart, and keep progress on the correct row after sorting.
- Selecting Atmos (or another audio quality) is the effective download quality even when a fallback preset is selected.
- The Quality column can show the downloaded result.
- Settings and account controls are locked during an active download; closing the window cancels the transfer first.

### Packaging

- CLI startup regression tests use a real isolated configuration directory and verify file logging.
- Development uses `working`, with verified changes merged into `main` before tagging releases.
- Tag releases now run CI, then build, then publish through a reusable workflow instead of a `GITHUB_TOKEN` release event that GitHub would ignore.
- Local `build.sh` installs the GUI extra and runs tests before building executables.
- Current credential and queue filenames are ignored by git and Docker.

## 2026.9.4.0 - 2026-09-04

### GUI

- Queue items added while a download is already active are processed in the same run instead of being left pending.
- The desktop app now advertises its Tidekeeper application and desktop-file identity and uses the installed theme icon when available.

## 2026.9.2.0 - 2026-09-02

### GUI

- Redesigned as a single workspace: find bar (Search or Links), results and the queue are always visible; Settings and Account open in a side panel instead of separate pages.
- New dark visual system with one accent, 30px control density, in-table empty states, status dots and slim progress bars in the queue.
- Queue log is a toggle inside the queue panel and opens automatically when a download fails.
- Keyboard: `Ctrl+F` focuses search, `Enter` queues selected results, `Delete` removes queue rows, `Ctrl+,` opens Settings, `Esc` closes the panel.
- Artist drill-down offers **Tracks** and **Videos** buttons when one artist row is selected; double-clicking a non-artist result queues it.
- Removed the separate "Update terminal" action; **Update** upgrades the full install.
- Starting a download applies unsaved quality settings in memory instead of saving, so it no longer signs you out when the client changed.
- Album + video downloads keep the combined progress total instead of jumping to 100% when the video pass begins.

### Reliability

- HTTP 429 retries no longer consume the normal attempt budget; instead the total rate-limit wait per request is capped at 90s. Catalog, playback, and OpenAPI manifest requests share one back-off implementation.
- OpenAPI manifest requests again stop after six "asset not ready" retries instead of up to 64.
- Artist lookup during album search reads a full page (50) of artists instead of 10.
- `{Duration}` and `{ReleaseDate}` path tokens strip Windows-illegal characters.
- Progress callback failures and size-probe fallbacks are logged at debug level instead of being silently discarded.

### Packaging

- PyPI publish uses OIDC trusted publishing when `PYPI_API_TOKEN` is not set.

## 2026.8.31.0 - 2026-08-31

### Path tokens

- Added `{TrackArtistID}`, `{TrackArtistName}`, `{VideoArtistID}`, and `{VideoArtistName}` for the primary artist on track and video filenames.
- `{ArtistID}` now works in track file formats (comma-separated list of all track artist IDs).
- Existing `{ArtistName}` (primary artist) and `{ArtistsName}` (all artists) on tracks and videos are unchanged.

## 2026.8.18.0 - 2026-08-18

### GUI

- Device login no longer reports success from a leftover token, and polling stops when the code expires.
- Changing the TIDAL client in Settings signs you out so the next search does not 4022.
- Queue progress no longer resets when album videos start, double-counts on CDN resume, or stays blank during parallel downloads.
- Artist double-click now honours **Include EPs and singles**.

### Reliability

- Videos are remuxed to MP4 with ffmpeg when it is available (default quality 720p).
- Playlist album lookup failures no longer abort the rest of the playlist.
- Atmos misses from transient 403/404s are no longer cached for the whole session, so **Retry Failed** can recover.
- Incomplete 1-byte `.flac` leftovers are not treated as finished downloads.

## 2026.8.16.0 - 2026-08-16

### Search

- Catalog search no longer stops at the first 10 hits (pages of 50, up to 200).
- Searching an artist name with the Album filter now includes that artist's full album list, not just the top ranked search hits (#50).

### Reliability

- Settings and token files are written atomically and kept at mode 0600.
- Concurrent workers reuse a token refresh already completed by another thread.
- Permanent download errors such as HTTP 404 fail immediately instead of retrying for tens of seconds.
- Auth and catalog calls reject invalid JSON and honor Retry-After on server errors.
- Stream cache evicts least-recently-used entries instead of scanning the full cache.

### Packaging and cleanup

- Removed unused `pydub` and `lxml` runtime dependencies.
- Dropped leftover tidal-dl translation keys and dead debug helpers.

## 2026.8.13.0 - 2026-08-13

### GUI

- Queue rows now show download progress, transfer speed, and ETA. Albums and playlists report track position (for example `4/12`).
- Added **Retry Failed** to re-queue only failed items. **Start Queue** skips completed rows.
- Direct Input accepts multi-line or comma-separated URLs/IDs, and expands `.txt` lists into separate queue rows.

### Performance

- Track downloads reuse the already-probed CDN size instead of making a second HEAD/Range probe.

## 2026.8.5.0 - 2026-08-05

### Reliability and packaging

- Invalid settings and token files now fall back safely instead of crashing startup.
- Settings instances no longer share mutable audio-quality priority state.
- In-app updates now time out after 10 minutes instead of potentially hanging indefinitely.
- Aligned the PrettyTable dependency constraint between `setup.py` and `requirements.txt`.

### Additional fixes

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
