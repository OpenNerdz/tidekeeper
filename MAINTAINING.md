# Maintaining this fork

This fork is intended for maintenance, packaging, and compatibility work around
the Python app published as `tidekeeper`.

## Scope

- Keep installation, packaging, terminal startup, and GUI startup working on supported Python versions.
- Improve reliability around authenticated API requests, retries, timeouts, partial files, and error reporting.
- Keep CI green for import, compile, terminal, and GUI smoke tests.
- Do not add behavior intended to bypass access controls, subscription checks, or DRM.

## Local development

```bash
cd TIDALDL-PY
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
python -m compileall -q tidal_dl
python -m unittest discover -s tests
python -m tidal_dl --help
tidekeeper --help
```

## Build

```bash
./build.sh
```

Build outputs are written under `TIDALDL-PY/dist` (Python distributions and
PyInstaller work) and `TIDALDL-PY/exe` (terminal and GUI executables).

## Release checklist

1. Update the version in `TIDALDL-PY/tidal_dl/printf.py`.
2. Move `CHANGELOG.md` entries from Unreleased into a new version section.
3. Run the local development checks and the test suite.
4. Confirm GitHub Actions CI passes on `main`.
5. Confirm the GitHub `pypi` environment exists and PyPI trusted publishing is
   configured for repository `OpenNerdz/tidekeeper`, workflow
   `.github/workflows/publish.yml`, environment `pypi`.
6. Tag the release (`git tag vX.Y.Z.N && git push origin vX.Y.Z.N`). The Build
   workflow creates the GitHub release and attaches terminal and GUI binaries.
7. Confirm the release's Publish workflow succeeds and the package appears on
   PyPI. Do not advertise `pip install tidekeeper` before the first successful
   publication.
