#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR/TIDALDL-PY"

rm -rf build dist exe release-assets *.egg-info tidekeeper.spec tidekeeper-gui.spec

python -m pip install --upgrade build pyinstaller
python -m pip install -e '.[gui,dev]'
python -m ruff check tidal_dl tests
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests
python -m build
pyinstaller -F tidal_dl/__main__.py -n tidekeeper
./dist/tidekeeper --help

GUI_FLAGS=()
if [[ "${OSTYPE:-}" != linux* ]]; then
  GUI_FLAGS+=(--windowed)
fi
pyinstaller -F "${GUI_FLAGS[@]}" tidal_dl/gui_app/__main__.py -n tidekeeper-gui

mkdir -p exe
for name in tidekeeper tidekeeper-gui; do
  if [[ -f "dist/${name}.exe" ]]; then
    cp "dist/${name}.exe" "exe/${name}.exe"
  else
    cp "dist/${name}" "exe/${name}"
  fi
done
