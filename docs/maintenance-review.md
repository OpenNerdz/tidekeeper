# Maintenance review

Reviewed from GitHub commit `bce2672` in September 2026.
These maintenance changes are included in release `2026.9.9.0`.

## Coverage

The starting repository contains 99 tracked files: 68 Python files, eight YAML
files, 19 other text files, and four PNG assets. The review included the CLI,
download backend, API client, settings and credential storage, desktop backend,
widgets and styling, tests, localization, installers, packaging, CI, and docs.
Every tracked text file was checked for readability; all Python files parsed,
all YAML files parsed, and all PNG headers had valid dimensions.
Workspace/account/settings screenshots were inspected and regenerated in Ubuntu
proot using the application theme. All 22 languages provide the 68 translation
keys referenced by the application.

This is a maintenance review with targeted fixes and regression coverage, not
a guarantee that every possible defect has been eliminated. The modified desktop
application was exercised with offscreen Qt tests and interaction checks in
Ubuntu proot.

## Fixed findings

| Area | Finding and change |
| --- | --- |
| Diagnostics | The write check overwrote and deleted a predictable filename. It now uses an automatically cleaned temporary file and verifies that writes flush. |
| Termux installer | Removed pip's attempt to upgrade itself; the installer explicitly obtains `python-pip` from the package manager. |
| Arch installer | Replaced the partial-upgrade command with a synchronized full upgrade when installing dependencies. |
| Docker / environment | `TIDEKEEPER_DOWNLOAD_PATH` was ignored outside Termux. Fresh profiles now honor it on every platform. Explicit empty environment mappings no longer read host values. |
| Batch input | Replaced duplicate CLI/GUI parsing with a shared iterative parser. It handles cycles, symlinks, relative nested lists, UTF-8 BOMs, comments, whitespace and commas, and deduplicates inputs without recursive Python calls. Unreadable lists produce a useful error. |
| Batch execution | A lookup failure or nested list could stop processing later inputs. Lookup failures now preserve the batch failure result while allowing remaining inputs to run. |
| Settings | Missing or damaged files could retain previously loaded values. Reads now reset instance state. Reload in the GUI actually reads the saved file and invalidates login when the configured client changes. |
| Credentials | Manual login without a refresh token reused an old session's refresh token. It now clears the old token. Token files reject numeric/bool credentials while retaining numeric user IDs. |
| Download cleanup | File assembly now checks cancellation between chunks. Assembly and FLAC remux remove temporary output on cancellation and preserve source parts for retry. |
| Catalog performance | A full final page triggered an unnecessary extra API request. Pagination stops as soon as the advertised total is reached. |
| Desktop logs | Logs are bounded to 2,000 blocks, use plain text, and do not force a user reading older download output to the bottom. Worker exception messages are redacted. |
| Queue state | Cancelled, interrupted, and partial items are no longer counted as queued. Retrying resets stale progress/quality. Summary counts use a single pass and escape message markup. |
| Desktop usability | Queue columns reserve more room for titles, users can resize preset columns, and tooltips expose full cell contents. Form controls have accessible labels. Empty searches and cancellation/naming hints describe the actual behavior. |
| Test isolation | Runtime-settings tests leaked paths, client state and other options into later tests. Full state restoration removes this order dependence and the observed `/tmp` write warning on Termux. |
| Build maintenance | Platform builds no longer delete the tracked package manifest and now smoke-test the packaged terminal executable. CI also checks `build.sh` syntax. Unused imports were removed where safe. |

Installer behavior was checked against the upstream
[Termux pip restriction](https://github.com/termux/termux-packages/blob/master/packages/python-pip/install_py_preventing_pip_from_installing.patch)
and [Arch maintenance guidance](https://wiki.archlinux.org/title/System_maintenance#Partial_upgrades_are_unsupported).
Installer regression tests replace system commands with recording functions;
they do not install or upgrade device packages.

## Validation

- Ubuntu 26.04 ARM64 under proot, Python 3.14.4, PySide6 6.11.2: all **302 tests passed with no skips**.
- The GUI interaction/screenshot script passed and generated workspace, settings, and account screenshots. The images were visually inspected and copied into `docs/screenshots`. The script now applies the same application theme as normal GUI startup.
- Termux Python 3.13: 276 tests passed, with the 26 Qt-dependent tests skipped there. Ubuntu covers those previously skipped tests.
- Ruff, Python compilation, YAML parsing, and shell syntax checks passed.
- Editable installation, module/CLI help commands, source distribution and wheel builds passed in Linux. Twine's strict checks passed for both distributions with its current dependencies.
- PyInstaller built terminal and GUI executables for Linux ARM64. The terminal executable passed its `--help` startup check. The GUI executable loaded the offscreen Qt plugin, remained running in demo mode for a 12-second startup check, and was then stopped by the test timeout without a Python traceback. Binaries are saved in `TIDALDL-PY/exe`; they run inside Linux/proot, not directly under Termux's Android runtime.
- The Linux validation environment is `/opt/tidekeeper-review` inside the existing `ubuntu` proot container. The Termux environment is `TIDALDL-PY/.venv`. Neither replaces the device's global Tidekeeper installation.

## Remaining verification limits

- Offscreen Qt tests cover application behavior and rendering, but not a physical desktop display, window manager, native file dialogs, or user input hardware.
- Docker runtime behavior and Windows/macOS executable builds still need their respective environments. Linux proot shares the Android kernel and does not validate a Docker daemon or other operating systems.
- Live account login, catalog requests, and downloads were not exercised. Backend regression tests use controlled responses and local fixtures.
- Dependency versions were validated by installation/build resolution; this was not a complete transitive dependency vulnerability audit.

## Local follow-up review — 2026-09-09

Updated the local checkout from `30b794f` to GitHub `main` at `7b4bf66`
(12 incoming commits), preserving the existing `setup.py` classifier edit.
The follow-up changes are on the local `working` branch, whose upstream was at
the same commit. These changes are prepared for release `2026.9.9.1`.

Reviewed the API and transfer backend, CLI, desktop queue and workers, saved
state, manifests, path generation, packaging, installers, and CI. Repository-wide
lint and parsing also cover the remaining Python code, including localization.
The changes focus on concrete failures and explicit module dependencies.

| Area | Fix and evidence |
| --- | --- |
| CDN retries | Removed retries hidden in the transport adapter and made the transfer loop own its retry budget. A persistent HTTP 503 now produces four request calls in the regression test, versus sixteen through the previous nested loops. |
| Rate limits | Exhausted waits stop immediately and do not restart at another playback endpoint. Zero waits cannot leave the wait budget unchanged forever. Shared parsing accepts HTTP dates and rejects negative or nonfinite delays. |
| HTTP response handling | Catalog and manifest responses close on success and error; artwork failures return no image data. Cancellation is checked before OAuth requests. Non-object error bodies retain their HTTP error instead of failing during dictionary access. |
| Download integrity | A one-byte range response with unknown total length no longer becomes the expected full file size. Empty transfers are rejected before promotion. Restarted transfers no longer credit the same bytes twice. |
| Desktop queue | Removal slots enforce the active-download guard, including calls through the Delete shortcut. Idle removal still works. |
| Saved profiles | Settings and tokens use explicit UTF-8 reading with BOM support. Invalid encoding clears stale in-memory values and logs a warning while leaving the source file intact. |
| Code structure | Replaced wildcard imports in the five core modules with explicit dependencies, removed unused imports and the obsolete size-only skip helper, and enabled lint checks for wildcard/unused imports, duplicate definitions, and unused locals. |

Retry handling was checked against the
[HTTP Retry-After specification](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3)
and [Requests adapter documentation](https://requests.readthedocs.io/en/stable/user/advanced/#automatic-retries).

### Follow-up validation

- Linux x86-64, Python 3.14, PySide6 6.11.2: **319 tests passed, no skips**.
  The original baseline was 302 tests; the new failure cases were observed before
  their fixes using controlled responses and temporary files.
- Ruff passed across the entire package directory, including scripts and setup.
  Package compilation and Python 3.10 grammar checks passed. All 22 languages
  provide the 68 directly referenced translation keys.
- All 103 tracked files passed text readability or PNG-signature checks; all
  tracked Python files parsed. Installer/build shell syntax and `git diff --check`
  passed.
- Offscreen desktop interaction checks passed; workspace, settings, and account
  screenshots were generated and visually inspected under
  `TIDALDL-PY/gui-screenshots/checkup/` (ignored build output).
- Module help, both terminal aliases, and doctor passed with an isolated profile.
  Dependency consistency passed with `pip check`.
- Source distribution and wheel builds, strict Twine checks, README metadata,
  and isolated installed-wheel startup passed. Build output is under
  `TIDALDL-PY/dist/checkup/` and is not a new release.

Live account authentication and TIDAL downloads were not exercised. Network
regressions use mocked responses or local HTTP fixtures. Physical desktop
behavior, Docker execution, and Windows/macOS builds remain outside this local
validation; this review does not certify the absence of all defects or assess
every transitive dependency for vulnerabilities.

### Desktop usability and cleanup follow-up

The additional desktop pass consolidates repeated queue insertion, search-worker
wiring, and demo settings conversion. It retains the existing workspace and
visual design while improving the common search, queue, and settings flows.

| Area | Change |
| --- | --- |
| Queue insertion | Equivalent catalog items and pasted TIDAL links reuse an unfinished job. Download now starts that existing job; completed items can still be queued again. Audio and videos-only collections remain distinct. |
| Queue recovery | Remove and Clear all support one level of undo, including sorted selections. Clear done keeps unfinished work. Retry incomplete includes failed, partial, interrupted, and cancelled jobs, and clears the previous attempt's details and quality. |
| Failure feedback | Selected queue rows show readable, selectable details that survive restart. Details are bounded and redacted before saving. Search errors appear inline; failed or partial downloads open the log without a blocking dialog. |
| Search | A running search exposes Cancel, interrupts cooperative waits, and suppresses late results. Real Qt worker tests verify completion callbacks run on the GUI thread. |
| Settings | Save is enabled for changed values, with an unsaved indicator in the header and footer. A failed disk save restores prior runtime settings before changing the login client. Demo save/reload shares conversion logic and preserves enum values. |
| Layout | Queue management moved to the footer. Narrow tables hide secondary columns to keep titles readable, retaining details in tooltips. At 1024 × 620 with Settings open, the tested layout needs no horizontal table scrolling. |

Validation on the same Linux x86-64 environment: **339 tests passed with no
skips**, including 20 additional GUI, worker, and saved-queue regressions.
Ruff, compilation, Python 3.10 grammar, dependency consistency, source/wheel
builds, strict Twine checks, and isolated installed-wheel GUI startup passed.
The screenshot interaction script also verifies queue undo. Workspace,
settings, and account screenshots were regenerated in `docs/screenshots`;
additional narrow-window Links and failure/unsaved-settings screenshots were
visually inspected under `TIDALDL-PY/gui-screenshots/ux/`.

These changes are prepared for release `2026.9.9.1`. The release workflow now
builds Linux ARM64 executables alongside Windows, macOS, and Linux x86-64.
Live TIDAL authentication/downloads and physical desktop behavior still require
their respective environments.
