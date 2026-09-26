# Security Policy

## Supported Versions

Security fixes are made on the `main` branch and included in the next tagged
release. Users should update to the latest release before reporting issues.

## Reporting a Vulnerability

Please do not open a public issue for security-sensitive problems.

Report vulnerabilities through GitHub's private vulnerability reporting for this
repository, or contact the maintainers privately if that is unavailable. Include:

- The affected version or commit.
- The platform and install method.
- Steps to reproduce.
- The impact and any known workaround.

Redact access tokens, refresh tokens, cookies, account IDs, and personal data
from logs before sharing them.

## Token Handling

Tidekeeper stores TIDAL access and refresh tokens locally so it can reuse a
login session. Token files are written with owner-only permissions where the
platform supports POSIX file modes. Treat token files as secrets and avoid
including them in bug reports, screenshots, backups, or shell history.

Manual token entry is hidden, and application logs redact bearer/basic
credentials, token assignments, and signed URL queries. Redaction is a best
effort safeguard; inspect logs before sharing them. Media requests do not
inherit `.netrc` credentials, and authenticated API requests do not follow
redirects. Device sign-in links are restricted to TIDAL's HTTPS login hosts.

## Untrusted Input

Remote manifest and embedded artwork reads have size limits. Manifest expansion
and nested batch lists have aggregate limits as well. Media URLs and redirects
are checked before requests, including public-address checks and rejection of
HTTPS downgrades. These checks are application safeguards, not a network sandbox.

FFmpeg and ffprobe are invoked with supported input formats and the local-file
protocol only. Keep these separately installed tools updated through your
operating system. Tidekeeper's dependency audit does not scan external binaries.

Output filenames are sanitized and writers to the same destination are
serialized within one Tidekeeper process. Use separate output directories for
independent instances that may download the same content. The application runs
with your user's filesystem permissions; use trusted configuration/output
directories and do not run it as an administrator.

## Dependency Checks

CI runs `pip-audit` against the installed terminal and desktop dependencies.
GitHub Actions are pinned to commit IDs and tracked by Dependabot. A clean audit
means no matching published advisories were found at that time, not proof that
the software is free of vulnerabilities.
