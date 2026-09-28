# Maintaining this fork

This fork is intended for maintenance, packaging, and compatibility work around
the Python app published as `tidekeeper`.

## Scope

- Keep installation, packaging, terminal startup, and GUI startup working on supported Python versions.
- Improve reliability around authenticated API requests, retries, timeouts, partial files, and error reporting.
- Keep CI green for lint, import, compile, terminal, and GUI smoke tests.
- Do not add behavior intended to bypass access controls, subscription checks, or DRM.

## Local development

```bash
cd TIDALDL-PY
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m ruff check tidal_dl tests ../scripts
python -m compileall -q tidal_dl
python -m unittest discover -s tests
python -m tidal_dl --help
tidekeeper --help
tidekeeper --doctor
```

Keep `TIDALDL-PY/setup.py` `install_requires` aligned with
`TIDALDL-PY/requirements.txt` when changing dependencies.

## Build

```bash
./build.sh
```

Build outputs are written under `TIDALDL-PY/dist` (Python distributions and
standalone apps) and `TIDALDL-PY/exe` (terminal and GUI executables). The build
uses the active Python environment and the same tool requirement files as CI.
It validates metadata with Twine as well as running lint and tests.

On Ubuntu/Debian, local GUI builds need Qt's system libraries:

```bash
sudo apt-get install libegl1 libgl1 libxkbcommon-x11-0 libxcb-cursor0 \
  libxcb-icccm4 libxcb-keysyms1 libxcb-shape0
```

CI also installs `xvfb` and `xauth` to exercise the X11 desktop plugin. It captures
screenshots and smoke-tests the packaged Linux GUI under `xvfb-run`, so missing
desktop libraries cannot be hidden by an offscreen-only check.

PyInstaller analysis and packed archives are retained in the ignored
`TIDALDL-PY/.pyinstaller-work` directory to speed up repeated local builds.
Run `./build.sh --clean` after switching interpreters, changing Qt system
libraries, or to investigate a cache problem. Setuptools output is rebuilt from
scratch each time, so deleted source files cannot persist in a wheel. CI platform
builds still start on fresh runners.

## Branch workflow

Keep `main` as the only branch in `OpenNerdz/tidekeeper`. Start from an up-to-date
`main`, run local checks before pushing, and confirm CI after the push. Use a
fork for pull requests when outside review is needed.

## Automatic releases

Push application or build changes to `main`. The Build workflow handles versioning,
release notes, tagging, CI, native builds, checksums, attestations, and publication.
You do not need to edit the version, create a tag, or run a separate build first.
Documentation/test-only changes run CI without a new release when no application
changes are waiting to be published. Pull requests run CI without publishing.

Versions keep the existing `YYYY.M.D.N` format using UTC: the first release of a
new day is `.0`, then `.1`, `.2`, and so on. Tags keep the `v` prefix and asset
names are unchanged. The counter includes reserved tags from failed attempts;
a version is never recycled. A retry of the same preparation reuses its tag.

The workflow commits the version and changelog to `main` and creates the tag in
one atomic Git push. A competing push cannot be overwritten or leave half of
that update behind. The bot uses `GITHUB_TOKEN`, so its commit/tag do not trigger
another workflow. All checks and builds check out the exact prepared commit.
Pull the bot's changes before making your next push, as with any other change to
`main`.

CI and the five native platform builds run in parallel. Only after they all pass
does the workflow upload a complete **draft** GitHub release. It publishes the
validated Python distributions, checks their hashes on PyPI, and then makes the
GitHub release public. Nothing is promoted if required tests or builds fail.

### Release notes

Continue writing concise user-facing bullets under `CHANGELOG.md → Unreleased`
when useful. They become the versioned changelog entry and release notes. An
optional hidden title hint gives the release the same descriptive naming style
as existing releases:

```markdown
## Unreleased

<!-- release-title: Reliable downloads and faster builds -->

- Fix interrupted downloads on shared storage.
- Reduce repeated build work.
```

This produces a title such as
`v2026.9.28.1 — Reliable downloads and faster builds`. The hidden hint is removed
from the public release body. Without written notes, the workflow uses up to eight
unique commit subjects, removes merge/bot noise and conventional-commit prefixes,
and links the full comparison. It derives a short title from the first change if
no hint was supplied. Clear commit subjects keep this fallback useful; it does
not invent a prose summary or claim extra testing. Notes from unpublished
attempts carry forward into the next release.

A short validation paragraph and update instructions are added after the gates
pass. Historical changelog sections are retained.

### One-time configuration

- Keep `PYPI_API_TOKEN` set to a token with upload rights for `tidekeeper`.
- Keep the `pypi` environment available. Its protection rules, if added, apply
  before uploading to PyPI.
- Permit the workflow's `contents: write` jobs to update `main`, create tags, and
  publish releases. Branch rules that block bot pushes will stop preparation.

No personal access token or extra AI service is required by the workflow.

### Preview builds and recovery

- **Preview:** run Build manually on `main` with `publish` unchecked. It runs checks and
  builds artifacts without changing versions or publishing. For a production
  run from `main`, check `publish`; existing unpublished app changes are detected.
- **Failed build/upload:** use GitHub's **Re-run failed jobs**. Validated artifacts
  are retained for 30 days. A partial PyPI upload resumes only missing files and
  refuses to skip any existing file whose SHA-256 differs. An already public
  GitHub release is never turned back into a draft or overwritten.
- **Expired artifacts or changed code:** fix the cause and push a new application
  or build change. It receives a new version. Do not move an old tag or upload
  rebuilt, different bytes under an existing PyPI version.
- **Manual tags:** remain supported when the tag, package version, and changelog
  agree. Running Build on an existing prepared tag can recover its release.

Production runs are serialized and never cancelled midway by a newer push.
Superseded pending runs may be coalesced by GitHub; the newest run compares with
the last public release so unpublished changes are still included. Superseded
preparation skips publication. Concurrent Git push failures are retried up to
three times; persistent permission or service errors fail visibly.

## Workflow performance

- Main pushes run CI through Build once; PRs use the CI workflow directly.
- Each job has a timeout. Pip downloads are cached using package metadata,
  workflow files, and separate tool lists in `.github/requirements/`.
- Compressed binaries, distributions, and screenshots are uploaded without
  another compression pass. Screenshots expire in 7 days; build artifacts in 30.
- CI installs the built wheel outside the checkout and checks command startup
  and bundled GUI data. Publication reuses those exact validated distributions.
- Local workflow validation: run `actionlint` from the repository root and
  `python scripts/check-release.py --ref refs/tags/vYYYY.M.D.N` for a manual tag.

## Supporter list

The GUI's Supporters list represents stargazers, not code contributors.
`.github/workflows/supporters.yml` fetches all pages of GitHub's stargazer API
when someone stars the repository, every six hours, or on manual dispatch.
Scheduled runs also remove accounts that have unstarred; GitHub may delay runs.
The updater validates the whole response, sorts and deduplicates usernames, and
commits only changes to `supporters.json`. API failures preserve the old snapshot.

The app shows its bundled snapshot immediately, fetches the current file from
`main` in a background worker, and checks again when Account is reopened after
six hours. Refresh forces a fetch. Opening the panel repeatedly does not create
extra network requests. These reads do not need a GitHub token. The GitHub job
uses the repository's built-in token and does not trigger another CI run for
its generated-data commit.
