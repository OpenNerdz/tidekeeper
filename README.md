![Tidekeeper](assets/tidekeeper-banner.png?raw=1)

# Tidekeeper

Tidekeeper is an unofficial maintained fork of
[yaronzz/Tidal-Media-Downloader](https://github.com/yaronzz/Tidal-Media-Downloader),
with a reliable terminal workflow and optional desktop GUI. The primary command
is `tidekeeper`; `tidal-dl` remains available for compatibility.

[![CI](https://github.com/OpenNerdz/tidekeeper/actions/workflows/ci.yml/badge.svg)](https://github.com/OpenNerdz/tidekeeper/actions/workflows/ci.yml)
[![Build](https://github.com/OpenNerdz/tidekeeper/actions/workflows/build.yml/badge.svg)](https://github.com/OpenNerdz/tidekeeper/actions/workflows/build.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

## Install

Tidekeeper requires Python 3.10 or newer.

```bash
python -m pip install "git+https://github.com/OpenNerdz/tidekeeper.git#subdirectory=TIDALDL-PY"
tidekeeper
```

Linux and Termux users can use the installer:

```bash
curl -fsSL https://raw.githubusercontent.com/OpenNerdz/tidekeeper/main/install.sh | bash
```

For Android shared storage, run `termux-setup-storage` and optionally set:

```bash
export TIDEKEEPER_DOWNLOAD_PATH="/storage/emulated/0/Download/Tidekeeper"
```

## Usage

```bash
tidekeeper --help
tidekeeper --doctor
tidekeeper --paths
tidekeeper --open-output
tidekeeper --update
tidekeeper -l "https://tidal.com/browse/track/70973230"
tidekeeper --video-only -l "https://tidal.com/browse/artist/123456"
```

Dolby Atmos downloads are opt-in with `tidekeeper -q Atmos`. Custom filename
formats support tokens including `{ArtistName}`, `{ArtistID}`, `{StreamQuality}`,
and `{Codec}`.

Failed downloads are saved to `failed-tracks.txt` in the download folder and can
be retried with:

```bash
tidekeeper -l "/path/to/downloads/failed-tracks.txt"
```

## Desktop GUI

```bash
python -m pip install "tidekeeper[gui] @ git+https://github.com/OpenNerdz/tidekeeper.git#subdirectory=TIDALDL-PY"
tidekeeper-gui
```

The GUI provides login, search, queueing, downloads, settings, diagnostics, and
updates. It is also available through `tidekeeper --gui`.

| Search | Queue |
| --- | --- |
| ![Search screen](docs/screenshots/search.png) | ![Queue screen](docs/screenshots/queue.png) |

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup and checks,
[CHANGELOG.md](CHANGELOG.md) for release history, and
[SECURITY.md](SECURITY.md) for private vulnerability reporting.

```bash
git clone https://github.com/OpenNerdz/tidekeeper.git
cd tidekeeper/TIDALDL-PY
python -m pip install -e .
python -m unittest discover -s tests
```

Build release artifacts with `./build.sh` from the repository root.

## Project policy

Tidekeeper does not aim to bypass access controls, subscription checks, or DRM.
Use it only where permitted by law and applicable service terms. This project is
not affiliated with or endorsed by TIDAL or Block, Inc.

The original project was created by YaronH and contributors. See
[NOTICE](NOTICE) and [LICENSE](LICENSE) for attribution and licensing.
