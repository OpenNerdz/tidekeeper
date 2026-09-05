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

## Branch workflow

Keep exactly two branches in `OpenNerdz/tidekeeper`: `main` for verified releases
and `working` for new features and fixes. Start changes from an up-to-date
`working`, push there, and verify CI and all platform builds before merging to
`main`. Keep `working` after merging and fast-forward it to `main` when needed.
Delete obsolete branches only after confirming their commits are merged.

## Release checklist

1. Update the version in `TIDALDL-PY/tidal_dl/printf.py` (format `YYYY.M.D.N`).
2. Move `CHANGELOG.md` entries from Unreleased into a new version section.
3. Run the local development checks and the test suite.
4. Push to `working` and confirm GitHub Actions CI and all platform builds pass.
   Merge `working` into `main`, then confirm the checks on `main` pass.
5. Confirm the GitHub `pypi` environment exists and the `PYPI_API_TOKEN` repository
   secret is set (PyPI API token with upload rights for project `tidekeeper`).
   Optional: also register a trusted publisher on PyPI for OIDC fallback
   (workflow `.github/workflows/publish.yml`, environment `pypi`).
6. Tag the release and push the tag:

   ```bash
   git tag vX.Y.Z.N
   git push origin vX.Y.Z.N
   ```

   The Build workflow creates the GitHub release and attaches terminal and GUI
   binaries for Windows, macOS, and Linux. The Publish workflow uploads the sdist
   and wheel to [PyPI](https://pypi.org/project/tidekeeper/).
7. Confirm the release's Publish workflow succeeds and
   `pip install -U tidekeeper` installs the new version.
