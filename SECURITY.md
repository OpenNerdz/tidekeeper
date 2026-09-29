# Security policy

## Reporting a vulnerability

Please don't open a public issue for security problems. Report them through
GitHub's [private vulnerability reporting](https://github.com/OpenNerdz/tidekeeper/security/advisories/new)
and include:

- The affected version (`tidekeeper --version`) and how you installed it.
- Your platform, the steps to reproduce, and the impact.

Remove access tokens, refresh tokens, cookies, account IDs, and personal data
from anything you share. Fixes ship in the next release, so update before
reporting.

## Your login

Tidekeeper saves your TIDAL access and refresh tokens so you stay signed in.
`tidekeeper --paths` shows where. Treat that file like a password: keep it out of
bug reports, screenshots, shared backups, and shell history. It's written with
owner-only permissions where the platform supports them.

## Built-in safeguards

- Logs redact tokens, credentials, and signed URL parameters. Redaction is best
  effort, so check logs before sharing them.
- Pasted tokens are hidden in the terminal, and sign-in links are limited to
  TIDAL's HTTPS login hosts.
- Media downloads never send your login or `.netrc` credentials, reject private
  or local network addresses, and refuse HTTPS-to-HTTP redirects.
- Manifests, artwork, and link lists have size limits. DRM-protected streams are
  rejected rather than saved.
- Filenames are sanitized so downloads stay inside your download folder.
- ffmpeg and ffprobe only read local files in expected media formats. Keep them
  updated through your system's package manager.

These are application safeguards, not a sandbox. Run Tidekeeper as a normal user,
not an administrator, with configuration and download folders you trust.

Tidekeeper coordinates writes with 256 reusable lock slots rather than one file
per track. Local locks prefer a private per-user state folder and fall back to a
user-specific temporary folder when the home directory is unavailable. Linux
and Termux prefer `~/.local/state/tidekeeper/locks` unless `XDG_STATE_HOME` is
set; macOS prefers `~/Library/Caches/Tidekeeper/locks`, and Windows prefers
`%LOCALAPPDATA%\Tidekeeper\locks`.

For separate computers or containers, Tidekeeper also uses
`.tidekeeper-locks` at the configured download root. Unsupported shared locking
falls back to local coordination with a warning. Inactive per-track lock files
from older releases are removed after a grace period when that folder is next
used. Don't manually delete active lock files while Tidekeeper is running.

## Dependencies

CI audits Python dependencies with `pip-audit`, and GitHub Actions are pinned to
commit IDs and updated by Dependabot. A clean audit means no known advisories
matched at the time; it doesn't prove the absence of vulnerabilities.
