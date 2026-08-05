![Tidekeeper](assets/tidekeeper-banner.png?raw=1)

# Tidekeeper

Tidekeeper is an unofficial maintained fork of
[yaronzz/Tidal-Media-Downloader](https://github.com/yaronzz/Tidal-Media-Downloader),
with a reliable terminal workflow and optional desktop GUI. The primary command
is `tidekeeper`; `tidal-dl` remains available for compatibility.

[![CI](https://github.com/OpenNerdz/tidekeeper/actions/workflows/ci.yml/badge.svg)](https://github.com/OpenNerdz/tidekeeper/actions/workflows/ci.yml)
[![Build](https://github.com/OpenNerdz/tidekeeper/actions/workflows/build.yml/badge.svg)](https://github.com/OpenNerdz/tidekeeper/actions/workflows/build.yml)
[![PyPI](https://img.shields.io/pypi/v/tidekeeper.svg)](https://pypi.org/project/tidekeeper/)
[![Release](https://img.shields.io/github/v/release/OpenNerdz/tidekeeper?display_name=tag)](https://github.com/OpenNerdz/tidekeeper/releases/latest)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue.svg)](https://www.python.org/downloads/)

## Install

Tidekeeper requires **Python 3.10 or newer**.

**ffmpeg is recommended** for video downloads and optional FLAC remux
(`tidekeeper --doctor` reports whether it is available).

### From PyPI (recommended)

```bash
python -m pip install -U tidekeeper
tidekeeper --help
```

Desktop GUI:

```bash
python -m pip install -U "tidekeeper[gui]"
tidekeeper-gui
```

### From Git

```bash
python -m pip install -U "git+https://github.com/OpenNerdz/tidekeeper.git#subdirectory=TIDALDL-PY"
tidekeeper --help
```

### One-line installer (Linux / Termux)

```bash
curl -fsSL https://raw.githubusercontent.com/OpenNerdz/tidekeeper/main/install.sh | bash
```

For Android shared storage, run `termux-setup-storage` and optionally set:

```bash
export TIDEKEEPER_DOWNLOAD_PATH="/storage/emulated/0/Download/Tidekeeper"
```

### Prebuilt binaries

Terminal and desktop GUI executables for Windows, macOS, and Linux are attached
to each [GitHub Release](https://github.com/OpenNerdz/tidekeeper/releases).

### Docker

Build the image from the repository, then persist account configuration and
downloads with bind mounts. The image includes **ffmpeg**.

```bash
docker build -t tidekeeper .
docker run --rm -it \
  -v "$PWD/config:/config" \
  -v "$PWD/downloads:/downloads" \
  tidekeeper
docker run --rm \
  -v "$PWD/config:/config" \
  -v "$PWD/downloads:/downloads" \
  tidekeeper -l "https://tidal.com/browse/track/70973230"
```

The container runs as non-root UID `1000`. Ensure both host directories are
writable by that user. A GUI is not included in the container image.

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

Dolby Atmos downloads are opt-in with `tidekeeper -q Atmos` (or GUI audio quality
**Atmos**). TIDAL keeps Atmos mixes on separate catalog IDs that often report
quality `LOW` with an Atmos flag — search now labels those rows clearly, and
when Atmos quality is selected Tidekeeper will switch a stereo album/track pick
to the matching Atmos catalog release when one exists.

Failed downloads are saved to `failed-tracks.txt` in the download folder and can
be retried with:

```bash
tidekeeper -l "/path/to/downloads/failed-tracks.txt"
```

## Customizability
Custom filename formats are supported:
| Tokens  | Description  | Album | Track | Video | Playlist |
| ------------- | ------------- | ------------- | ------------- | ------------- | ------------- |
| {ArtistID}  | Comma separated list of each artists' ID for that media (i.e: ```123, 456```)  | :white_check_mark:  | :x:  | :white_check_mark:  | :x: |
| {ArtistName}  | Comma separated list of each artists' name for that media (i.e: ```ABC, DEF```)  | :white_check_mark:  | :x:  | :x:  | :x: |
| {ArtistName}  | Primary artist's name for that media | :x:  | :white_check_mark:  | :white_check_mark:  | :x: |
| {ArtistsName}  | Comma separated list of each artists' name for that media (i.e: ```ABC, DEF```)  | :x:  | :white_check_mark:  | :white_check_mark:  | :x: |
| {AlbumArtistID}  | Primary artist's ID for that media | :white_check_mark:  | :x:  | :x:  | :x: |
| {AlbumArtistName}  | Primary artist's name for that media | :white_check_mark:  | :x:  | :x:  | :x: |
| {Flag}  | Quality/content flags: `M` (Master), `A` (Dolby Atmos), `E` (Explicit) | :white_check_mark:  | :x:  | :x:  | :x: |
| {AlbumID}  |  | :white_check_mark:  | :x:  | :x:  | :x: |
| {AlbumYear}  |  | :white_check_mark:  | :white_check_mark:  | :x:  | :x: |
| {AlbumTitle}  |  | :white_check_mark:  | :white_check_mark:  | :x:  | :x: |
| {AudioQuality}  | Audio quality reported by TIDAL (e.g. `LOSSLESS`, `HI_RES`) | :white_check_mark:  | :white_check_mark:  | :x:  | :x: |
| {DurationSeconds}  |  | :white_check_mark:  | :white_check_mark:  | :x:  | :x: |
| {Duration}  | Duration formatted as `MM:SS` (or `H:MM:SS`) | :white_check_mark:  | :white_check_mark:  | :x:  | :x: |
| {NumberOfTracks}  |  | :white_check_mark:  | :x:  | :x:  | :x: |
| {NumberOfVideos}  |  | :white_check_mark:  | :x:  | :x:  | :x: |
| {NumberOfVolumes}  |  | :white_check_mark:  | :x:  | :x:  | :x: |
| {ReleaseDate}  |  | :white_check_mark:  | :x:  | :x:  | :x: |
| {RecordType}  |  | :white_check_mark:  | :x:  | :x:  | :x: |
| {TrackID}  |  | :x:  | :white_check_mark:  | :x:  | :x: |
| {TrackNumber}  |  | :x:  | :white_check_mark:  | :x:  | :x: |
| {TrackTitle}  |  | :x:  | :white_check_mark:  | :x:  | :x: |
| {ExplicitFlag}  |  | :x:  | :white_check_mark:  | :white_check_mark:  | :x: |
| {StreamQuality}  |  | :x:  | :white_check_mark:  | :x:  | :x: |
| {Codec}  |  | :x:  | :white_check_mark:  | :x:  | :x: |
| {VideoID}  |  | :x:  | :x:  | :white_check_mark:  | :x: |
| {VideoNumber}  |  | :x:  | :x:  | :white_check_mark:  | :x: |
| {VideoTitle}  |  | :x:  | :x:  | :white_check_mark:  | :x: |
| {VideoYear}  |  | :x:  | :x:  | :white_check_mark:  | :x: |
| {PlaylistUUID}  |  | :x:  | :x:  | :x:  | :white_check_mark: |
| {PlaylistName}  |  | :x:  | :x:  | :x:  | :white_check_mark: |

## Desktop GUI

The GUI provides login, search, queueing, downloads, settings, diagnostics, and
updates. After installing with the GUI extra above, launch it with
`tidekeeper-gui` or `tidekeeper --gui`. Update GUI installs with
`tidekeeper --update-gui`.

| Search | Queue |
| --- | --- |
| ![Search screen](docs/screenshots/search.png) | ![Queue screen](docs/screenshots/queue.png) |

| Settings | Account |
| --- | --- |
| ![Settings screen](docs/screenshots/settings.png) | ![Account screen](docs/screenshots/account.png) |

## Troubleshooting

Run diagnostics first:

```bash
tidekeeper --doctor
tidekeeper --paths
```

For repeated HTTP 429 errors, keep **Use request delay** enabled and raise
**Request delay seconds** to `30` or `60` before retrying.

If doctor warns that **ffmpeg** is missing, install it from your OS package
manager (or use the Docker image). Video downloads and FLAC remux may otherwise
be limited.

If Termux reports `cannot locate symbol "x265_api_get_216"`, refresh its media
packages with `pkg upgrade -y && pkg reinstall -y ffmpeg x265`. If that fails,
change mirrors with `termux-change-repo` and retry.

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
