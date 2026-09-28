# Contributing

Thanks for helping maintain Tidekeeper. Keep changes focused and include
tests for user-visible behavior or regressions.

## Development Setup

```bash
git clone --depth 1 https://github.com/OpenNerdz/tidekeeper.git
cd tidekeeper/TIDALDL-PY
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

The shallow clone is enough to build and test. Run `git fetch --unshallow` when
you need earlier history. On Windows, activate with `.venv\Scripts\activate`.

## Branches

The repository keeps only `main`. Maintainers run local checks before pushing
to `main` and confirm CI after the push. Contributors can open pull requests
from their forks; merge them after CI and relevant platform builds succeed.

## Checks

Run these before opening a pull request:

```bash
python -m pip install -e ".[dev]"
python -m ruff check tidal_dl tests ../scripts
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
bash -n ../build.sh
```

Ruff checks syntax errors, undefined names, bare `except`, unused imports and
locals, duplicate definitions, and wildcard imports. Use explicit imports so
undefined names cannot hide behind transitive dependencies. Prefer these checks
over large style-only refactors.

## Pull Request Guidelines

- Keep unrelated refactors out of feature and bug-fix pull requests.
- Add or update tests when fixing a bug.
- Redact tokens, cookies, account details, and personal data from logs.
- Update `README.md`, `SECURITY.md`, or release notes when behavior changes.
- Preserve compatibility with the `tidal-dl` command where practical.

## Release Notes

Release notes should summarize user-facing changes, fixes, and known migration
notes. Put concise bullets under `CHANGELOG.md → Unreleased`; an optional
`<!-- release-title: Short descriptive title -->` sets the release subtitle.
Otherwise clear commit subjects provide the automatic fallback. Main pushes
prepare the version and tag automatically; contributors do not need to bump them.
See [MAINTAINING.md](MAINTAINING.md) for builds, tagging, publishing, and recovery.
