import re
from pathlib import Path

from setuptools import find_packages, setup


ROOT = Path(__file__).parent
VERSION_FILE = ROOT / "tidal_dl" / "printf.py"
REPO_ROOT = ROOT.parent
README_FILE = ROOT / "README.md"
RAW_BASE = "https://raw.githubusercontent.com/OpenNerdz/tidekeeper/main/"
BLOB_BASE = "https://github.com/OpenNerdz/tidekeeper/blob/main/"
STAGED_FILES = ("README.md", "LICENSE", "NOTICE")


def get_version():
    match = re.search(r"^VERSION\s*=\s*['\"]([^'\"]+)['\"]", VERSION_FILE.read_text(), re.MULTILINE)
    if match is None:
        raise RuntimeError("Unable to find package version")
    return match.group(1)


def absolutize_links(text):
    """Point relative links at GitHub so they resolve on PyPI."""
    pattern = re.compile(r"(!?)\[([^\]]*)\]\(([^)\s]+)\)")

    def repl(match):
        bang, label, target = match.groups()
        if re.match(r"^(https?:|mailto:|#)", target):
            return match.group(0)
        base = RAW_BASE if bang else BLOB_BASE
        return "{}[{}]({}{})".format(bang, label, base, target.lstrip("./"))

    return pattern.sub(repl, text)


def stage_repo_files():
    """Copy shared repo files into the package dir so they reach the sdist.

    The package lives in a subdirectory, so files at the repository root are
    otherwise absent from the sdist, and any wheel built from that sdist loses
    its long description. Building from an unpacked sdist is a no-op here
    because the staged copies already exist.
    """
    for name in STAGED_FILES:
        source = REPO_ROOT / name
        if not source.exists():
            continue
        target = ROOT / name
        content = source.read_text(encoding="utf-8")
        if name == "README.md":
            content = absolutize_links(content)
        if not target.exists() or target.read_text(encoding="utf-8") != content:
            target.write_text(content, encoding="utf-8")


def get_long_description():
    stage_repo_files()
    if README_FILE.exists():
        return README_FILE.read_text(encoding="utf-8")
    return "Maintained Tidal-Media-Downloader fork with terminal and desktop GUI workflows."


setup(
    name='tidekeeper',
    version=get_version(),
    license="Apache-2.0",
    description="Maintained Tidal-Media-Downloader fork with terminal and desktop GUI workflows.",
    long_description=get_long_description(),
    long_description_content_type="text/markdown",

    author='Tidekeeper maintainers',
    url="https://github.com/OpenNerdz/tidekeeper",
    project_urls={
        "Source": "https://github.com/OpenNerdz/tidekeeper",
        "Changelog": "https://github.com/OpenNerdz/tidekeeper/blob/main/CHANGELOG.md",
        "Issues": "https://github.com/OpenNerdz/tidekeeper/issues",
        "Upstream": "https://github.com/yaronzz/Tidal-Media-Downloader",
    },

    packages=find_packages(),
    include_package_data=False,
    platforms="any",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Console",
        "Environment :: X11 Applications :: Qt",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
        "Topic :: Multimedia :: Sound/Audio",
        "Topic :: Multimedia :: Video",
    ],
    keywords="tidal music downloader cli gui lossless atmos",
    python_requires=">=3.10",
    # Keep pins aligned with requirements.txt (single source of intent).
    install_requires=[
        "aigpy>=2022.7.8.1",
        "requests>=2.34.2",
        "pycryptodome",
        "prettytable>=3.18.0",
    ],
    extras_require={
        "gui": ["PySide6>=6.5"],
        "dev": ["ruff>=0.8.0"],
    },
    entry_points={'console_scripts': [
        'tidekeeper = tidal_dl:main',
        'tidal-dl = tidal_dl:main',
        'tidekeeper-gui = tidal_dl.gui_app.__main__:main',
    ]}
)
