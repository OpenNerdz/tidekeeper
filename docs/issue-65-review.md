# Issue #65 review and local fix

Reviewed 2026-09-17 against `b3aa96f` on `working`.

## Why the closed issue was still failing

[Issue #65](https://github.com/OpenNerdz/tidekeeper/issues/65) was closed on
September 15. The reporter's September 17 follow-up shows a successful fresh
login on `2026.9.17.0`, a US account, and Master quality, followed by playback
HTTP 404 / subStatus 4022 and an immediate logout. The maintainer's later reply
says the problem could not be reproduced on their accounts.

The earlier releases replaced the bundled client and tracked which client
issued a token, but left these confirmed defects in place:

1. A playback-only 4022 refreshed and then erased the entire saved session.
   That response does not establish whether session or catalog access works.
   Its error classification also prevented alternate manifests and configured
   quality fallbacks. An existing regression test explicitly expected deletion.
2. Master still sent the legacy `HI_RES` request and required an exact Master
   response, rejecting modern FLAC even when available. TIDAL
   [retired MQA in July 2024](https://support.tidal.com/hc/en-us/articles/25876825185425-Audio-Format-Updates).
3. After catalog client rejection cleared a session, automatic host fallback
   could send another request with `Bearer None`.
4. Live verification exposed a second download defect: OpenAPI supplied a
   DRM-protected high-resolution DASH manifest, which the parser accepted as
   clear audio. The resulting encrypted file was tagged and marked complete
   even though a decoder rejected it. The standard endpoint offered an
   unencrypted lossless FLAC stream for the same track.

These are reproducible application defects. They do **not** prove why TIDAL's
playback service returned 4022 for the reporter's particular client/account.
The bundled client's display-only format label is not sufficient evidence to
disable modern high-resolution FLAC for every account, so it is not used as a
new global capability restriction.

## Changes

- Classify playback and OpenAPI manifest client rejections separately from
  catalog/session failures. Keep the token file and in-memory login unchanged
  on playback 4022, and allow alternate manifest and configured quality attempts.
- Stop repeated usage/format permutations after an OpenAPI client rejection.
  Continue to enforce rate-limit budgets and cancellation.
- Resolve a single legacy Master selection as Max, then HiFi. Multiple-quality
  orders keep their order, with Master replaced by Max and duplicates removed.
  Other single-quality requests remain strict; the Master migration never
  silently accepts AAC. Preserve actual quality and original request labels.
- Retain client-change protections and catalog rejection cleanup, but stop
  host fallback after clearing the unusable login.
- Report endpoint, client label, country, and quality without response bodies
  or credentials. Replace the misleading logout hint for playback failures.
  Use structured HTTP status for rate-limit classification so a track ID
  containing `429` cannot suppress fallback.
- Reject DASH manifests containing `ContentProtection` before extracting
  segment URLs. Report the format as unsupported so the existing quality order
  can select an available clear stream. No DRM handling or decryption was added.

## Verification

- The first issue-specific test run exposed 11 failures/errors in 12 cases
  before the fix. Live testing subsequently exposed six failing assertions
  covering protected manifests and the clear-lossless fallback. The completed
  regression file now covers 19 cases.
- After the cleanup below, Python 3.13 on Termux: 372 tests, 327 passed and
  45 Qt-dependent skips.
- Python 3.14 in local Ubuntu with PySide6: all 372 tests passed, no skips.
- Real localhost HTTP integration: device authorization, token exchange,
  catalog access, playback 4022, OpenAPI 4022, HiFi recovery, actual generated
  FLAC transfer, metadata tagging, completion receipt, successful session
  verification, and retry without downloading the file again.
- Ruff, bytecode compilation, all three terminal help commands, and the
  desktop screenshot/interaction smoke checks passed.
- Source distribution and wheel build, strict package metadata checks, and
  isolated wheel installation/import/terminal smoke checks passed.

Run the focused regressions from `TIDALDL-PY` with:

```sh
python -m unittest discover -s tests -p test_playback_client.py
```

## Requested cleanup

- Removed disabled bundled clients; selectors now use explicit, stable IDs
  `1` and `4`, preserving the current login and existing profiles.
- Centralized quality order and Master-to-FLAC migration. Desktop settings
  present modern qualities while preserving legacy lossless fallbacks.
- Consolidated CLI help and generated translated quality prompts from the
  actual choices, including Atmos and 240p. Removed obsolete prompt strings.
- Removed unused playlist/cover/progress helpers, a redundant file-input
  wrapper, stale demo client/language lists, and the old issue-18 live script.
  `requirements.txt` now supplies the package's runtime dependencies directly.
- Moved approximately 280 MiB of ignored, regenerable build outputs from
  `TIDALDL-PY/build`, `dist` and `exe` to Trash. Configuration, music and Git
  history were left intact; deleted tracked code remains recoverable from Git.
- Added sparse-client-ID, current-quality-menu and legacy-settings tests.
  Rechecked source/wheel builds, strict metadata, installed CLI/GUI startup,
  GUI interactions, and live saved-login/stream-resolution/retry after cleanup.

## Live verification

The user completed a fresh device login in an isolated local test profile. The
account reports country `GB`. The real CLI downloaded track `465909959`,
"LOST MY MIND IN PARIS", with the saved quality set to Master and no explicit
fallback list.

The first live attempt exposed the protected-DASH defect described above. Its
unplayable output and completion receipt were moved into a separate
`rejected-protected-output` directory within the test profile for inspection;
they are no longer in the download folder.

After adding the manifest guard, the same CLI request completed using the
available unencrypted HiFi stream:

- FLAC, 16-bit, 44,100 Hz, stereo, 189.472 seconds; 20,784,678 bytes including tags.
- Metadata written successfully; receipt size and SHA-256 match the file.
- Full independent FFmpeg decoding with `-xerror -err_detect explode` exited 0
  without errors, using the local Ubuntu runtime.
- A second CLI invocation skipped the completed file. Its size and modification
  time remained unchanged.
- Session verification succeeded after the download and after the retry;
  no additional login was required.

The Termux FFmpeg installation itself has a separate dynamic-linker error in
`libplacebo.so`. The final clear FLAC download did not require remuxing and
completed without that tool; this review did not change system packages.

No live 4022 response occurred on this GB account. Its recovery path is covered
by the automated HTTP tests, but the original reporter's US-account behavior
still requires confirmation. The live test establishes a playable result for
the reported track and settings on the authorized GB account.

This is a local, unreleased change. No GitHub comment, issue state change,
push, or release was made as part of this review.
