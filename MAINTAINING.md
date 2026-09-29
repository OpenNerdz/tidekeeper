# Maintaining Tidekeeper

Tidekeeper is published to PyPI as `tidekeeper`. Maintenance focuses on:

- Installation, packaging, and terminal/desktop startup on every supported Python.
- Reliable authentication, retries, timeouts, resumable transfers, and clear errors.
- Green CI for lint, tests, packaging, and platform builds.
- Never adding behavior that bypasses access controls, subscription checks, or DRM.

## Local checks

From `TIDALDL-PY`, with a virtual environment active:

```bash
python -m pip install -e ".[gui,dev]"
python -m ruff check tidal_dl tests ../scripts
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests
tidekeeper --help && tidekeeper --doctor
```

Runtime dependencies live only in `TIDALDL-PY/requirements.txt`; `setup.py`
reads them from there. Validate workflow edits with `actionlint`.

## Build

```bash
./build.sh           # lint, test, sdist/wheel, twine check, standalone apps
./build.sh --clean   # also reset the cached PyInstaller work
```

Python distributions and standalone apps are written to `TIDALDL-PY/dist`, and
copies of the executables to `TIDALDL-PY/exe`. PyInstaller work is cached in
`TIDALDL-PY/.pyinstaller-work`; clean it after switching Python or Qt libraries.
Linux GUI builds need Qt's system libraries:

```bash
sudo apt-get install libegl1 libgl1 libxkbcommon-x11-0 libxcb-cursor0 \
  libxcb-icccm4 libxcb-keysyms1 libxcb-shape0
```

## Releases

Keep `main` as the only permanent branch. Every push runs CI and all five
platform builds, but does not publish. When `main` is green and ready, run the
**Build** workflow with **publish** checked. Don't edit the version or create
tags by hand.

1. The Build workflow picks the next `YYYY.M.D.N` version (UTC date, then a daily
   counter that never reuses a published number), moves `CHANGELOG.md →
   Unreleased` into a dated section, and pushes that bot-authored commit to a
   transient `release-candidate` branch.
2. CI and the five platform builds run in parallel on that exact candidate.
3. Only after everything passes does the workflow advance `main`, publish to
   PyPI, and verify both distribution hashes. It then creates the immutable tag
   and public GitHub release with checksums and provenance attestations.

Only installed package or dependency changes make a release eligible. Docs,
tests, workflows, release scripts, installers, Docker, and build tooling wait for
the next package release, so they never create an update prompt by themselves.
Pull requests run checks only; normal pushes also build platform previews. Pull
the bot's release commit after publishing and before your next push.

### Release notes

Add concise, user-facing bullets under `## Unreleased` in `CHANGELOG.md`. An
optional hidden hint sets the release title:

```markdown
## Unreleased

<!-- release-title: Reliable downloads and faster builds -->

- Fix interrupted downloads on shared storage.
```

This produces `v2026.9.28.1 — Reliable downloads and faster builds`. Without
notes, the workflow summarizes up to eight commit subjects, so write clear ones.
Notes from unpublished attempts carry forward to the next release.

### One-time configuration

- Repository secret `PYPI_API_TOKEN` with upload rights for `tidekeeper`.
- A `pypi` environment. Protection rules on it apply before the upload.
- Permission for workflow jobs with `contents: write` to push to `main`, create
  tags, and publish releases. Branch rules that block the bot stop releases.

### Previews and recovery

- **Preview build:** push to `main`, or run Build manually with `publish`
  unchecked. Check `publish` to release unpublished package changes from `main`.
- **Failed build or upload:** use **Re-run failed jobs**. Artifacts are kept for
  30 days. PyPI uploads resume missing files and never replace a file whose hash
  differs. If `main` was already promoted, finish that release before adding a
  newer release candidate.
- **Expired artifacts before promotion:** fix the cause and push again, then run
  a fresh production build. Never move a tag or upload different files under an
  existing version.
- **Tags:** the release workflow creates them after PyPI verification. Do not
  push release tags manually; `scripts/check-release.py` is only a validator for
  an existing tag.

Production runs are serialized and never cancelled midway. A newer push that
supersedes a pending run is still included, because each run compares with the
last public release.

## Supporter list

The desktop app's Supporters list shows the repository's stargazers.
The app shows the bundled `supporters.json` snapshot immediately and refreshes
the current list from GitHub in the background without a token. No automation
writes supporter commits to `main`. Refresh the bundled offline snapshot with
`scripts/update-supporters.py` as part of an ordinary reviewed change when
needed.
