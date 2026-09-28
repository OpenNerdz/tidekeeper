#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR/TIDALDL-PY"

case "${1:-}" in
  --clean) rm -rf .pyinstaller-work; shift ;;
  --help|-h) echo "Usage: ./build.sh [--clean]"; exit 0 ;;
esac
if [[ $# -ne 0 ]]; then
  echo "Usage: ./build.sh [--clean]" >&2
  exit 2
fi

# Keep PyInstaller's dependency analysis and packed archives between builds.
# Setuptools output is always fresh so removed modules cannot leak into wheels.
rm -rf build dist exe release-assets *.egg-info tidekeeper.spec tidekeeper-gui.spec

python -m pip install -r ../.github/requirements/build.txt \
  -r ../.github/requirements/package.txt -e '.[gui,dev]'
python -m ruff check tidal_dl tests ../scripts
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests
python -m build
python -m twine check --strict dist/*
python -m PyInstaller --workpath .pyinstaller-work -F tidal_dl/__main__.py -n tidekeeper
./dist/tidekeeper --help

GUI_FLAGS=()
if [[ "${OSTYPE:-}" != linux* ]]; then
  GUI_FLAGS+=(--windowed)
fi
python -m PyInstaller --workpath .pyinstaller-work -F "${GUI_FLAGS[@]}" \
  --add-data "tidal_dl/gui_app/supporters.json:tidal_dl/gui_app" \
  tidal_dl/gui_app/__main__.py -n tidekeeper-gui

mkdir -p exe
for name in tidekeeper tidekeeper-gui; do
  if [[ -f "dist/${name}.exe" ]]; then
    cp "dist/${name}.exe" "exe/${name}.exe"
  else
    cp "dist/${name}" "exe/${name}"
  fi
done
