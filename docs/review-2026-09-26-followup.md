# Release review follow-up — 2026.9.26.1

This patch addresses the review of 2026.9.26.0, released in PR #72.

| Finding | Resolution and verification |
| --- | --- |
| Scheme-less TIDAL links stopped working | Restore HTTPS normalization only for the exact supported TIDAL hosts. CLI, batch, desktop Links, and desktop search regressions cover these inputs while retaining host and ID validation. |
| Video playlists might omit ENDLIST | A live catalog video downloaded successfully after normal device authorization. Its media playlist contained both VOD and ENDLIST. Explicitly immutable VOD playlists without ENDLIST are now supported too; a generated HLS fixture exercises real transfer assembly and FFmpeg finalization. Growing playlists remain rejected. |
| Cancelling device login invalidated other work | Device grants now have their own generation counter. Cancellation preserves saved-session refreshes, catalog searches, and playback cache identity while invalidating stale challenges, grants, and polling replies. Successful new login still invalidates the previous session generation. |
| Closing appeared to do nothing | A persistent, accessible banner explains cancellation, pending requests, or an update that must finish. The work area is disabled while closing. Qt tests cover download/update waits and worker cleanup; the banner was visually inspected. |
| Destination locking was only process-local | Add cancellable OS locks through filelock, retaining the reentrant thread lock. Actual track/video download tests verify exclusion through completion-receipt writes. Process tests cover contention, cancellation, abrupt exit, and reentrancy; these regressions run on every build platform. |
| Download guards lacked coverage | Add encoding, unexpected-range, HTTPS downgrade, and normal HTTPS redirect tests. Reject compressed responses before discarding a valid partial file. |

## Live video check

- Public catalog URL: https://tidal.com/browse/video/122367840
- Catalog duration: 30 seconds; completed media duration: 30.058667 seconds.
- Completed MP4: 751,352 bytes, with audio and video streams verified by ffprobe.
- Master playlist: 1,525 bytes, no ENDLIST (normal for a master playlist).
- Media playlist: 3,663 bytes, both VOD and ENDLIST present.
- Used the normal saved-account/device-login flow and existing download path at
  240p into a temporary directory. Test media was removed afterward. No tokens,
  signed media URLs, or account identifiers are included here.

This verifies one real catalog sample, not every TIDAL video or entitlement.

## Checks

490 tests pass locally with Qt and FFmpeg enabled. Ruff, compilation, desktop
screenshots, and dependency auditing also pass. Native locking regressions are
part of each Linux, macOS, and Windows release build; CI and artifact results are
linked from the pull request and release.

Lock metadata lives in hidden `.tidekeeper-locks` folders and must not be removed
while instances are active. Coordination requires a filesystem with functioning
OS locks and cooperating versions of Tidekeeper. Other programs do not honor
these locks.

The VOD distinction follows [RFC 8216, section 4.3.3.5](https://www.rfc-editor.org/rfc/rfc8216.html#section-4.3.3.5).
Portable OS locking uses [filelock](https://py-filelock.readthedocs.io/en/latest/).
