# Contributing

Thanks for helping maintain Tidekeeper. Keep changes focused and include
tests for user-visible behavior or regressions.

## Development Setup

```bash
git clone https://github.com/OpenNerdz/tidekeeper.git
cd tidekeeper/TIDALDL-PY
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

## Branches

The repository keeps `main` and `working`. Add features and fixes on `working`
and open a pull request from `working` into `main` after local checks pass.
Merge only after CI and all platform builds succeed, and retain `working` for
subsequent development.

## Checks

Run these before opening a pull request:

```bash
python -m pip install -e ".[dev]"
python -m ruff check tidal_dl tests
python -m compileall -q tidal_dl
python -m unittest discover -s tests
python -m tidal_dl --help
tidekeeper --help
tidal-dl --help
```

For installer changes, also run:

```bash
bash -n ../install.sh
bash -n ../scripts/install-termux.sh
```

Ruff is configured for a high-signal subset of rules (syntax errors, undefined
names, bare `except`). Prefer fixing those over large style-only refactors.

## Pull Request Guidelines

- Keep unrelated refactors out of feature and bug-fix pull requests.
- Add or update tests when fixing a bug.
- Redact tokens, cookies, account details, and personal data from logs.
- Update `README.md`, `SECURITY.md`, or release notes when behavior changes.
- Preserve compatibility with the `tidal-dl` command where practical.

## Release Notes

Release notes should summarize user-facing changes, fixes, and known migration
notes. The release tag should match the version reported by `tidekeeper --help`.
