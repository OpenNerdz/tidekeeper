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
python -m ruff check tidal_dl tests
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
PyInstaller work) and `TIDALDL-PY/exe` (terminal and GUI executables).

## Release checklist

1. Update the version in `TIDALDL-PY/tidal_dl/printf.py` (format `YYYY.M.D.N`).
2. Move `CHANGELOG.md` entries from Unreleased into a new version section.
3. Run the local development checks and the test suite.
4. Push to `main` and confirm GitHub Actions CI passes.
5. Confirm the GitHub `pypi` environment exists. For trusted publishing, register
   this repository on PyPI as a trusted publisher for project `tidekeeper`:
   workflow `.github/workflows/publish.yml`, environment `pypi`.
6. Tag the release and push the tag:

   ```bash
   git tag vX.Y.Z.N
   git push origin vX.Y.Z.N
   ```

   The Build workflow creates the GitHub release and attaches terminal and GUI
   binaries for Windows, macOS, and Linux.
7. Confirm the release's Publish workflow succeeds and the package appears on
   PyPI. Only advertise `pip install tidekeeper` after the first successful
   publication; until then, document Git install and release binaries.
