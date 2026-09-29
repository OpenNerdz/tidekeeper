# Contributing

Thanks for helping improve Tidekeeper. Keep changes focused, and include tests
for bug fixes and user-visible behavior.

## Setup

```bash
git clone --depth 1 https://github.com/OpenNerdz/tidekeeper.git
cd tidekeeper/TIDALDL-PY
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -e ".[gui,dev]"
```

The shallow clone is enough to build and test; run `git fetch --unshallow` if you
need older history.

## Checks

Run these from `TIDALDL-PY` before opening a pull request:

```bash
python -m ruff check tidal_dl tests ../scripts
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests
tidekeeper --help
```

The desktop tests are skipped when PySide6 isn't installed, so install the `gui`
extra to run all of them. For installer or build script changes, also run
`bash -n` on `../install.sh`, `../scripts/install-termux.sh`, and `../build.sh`.

Ruff checks for real defects such as undefined names, unused imports, and bare
`except` clauses. Use explicit imports.

## Pull requests

- Keep unrelated refactoring out of feature and bug-fix changes.
- Add or update tests for the behavior you change.
- Remove tokens, cookies, account details, and personal data from logs and fixtures.
- Update `README.md` or the docs when user-facing behavior changes.
- Keep the `tidal-dl` command working where practical.

Add a short, user-facing bullet under `## Unreleased` in `CHANGELOG.md`. Merged
changes are versioned and released automatically; see
[MAINTAINING.md](MAINTAINING.md).
