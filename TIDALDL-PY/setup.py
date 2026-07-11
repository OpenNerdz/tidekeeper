import re
from pathlib import Path

from setuptools import find_packages, setup


ROOT = Path(__file__).parent
VERSION_FILE = ROOT / "tidal_dl" / "printf.py"
README_FILE = ROOT.parent / "README.md"


def get_version():
    match = re.search(r"^VERSION\s*=\s*['\"]([^'\"]+)['\"]", VERSION_FILE.read_text(), re.MULTILINE)
    if match is None:
        raise RuntimeError("Unable to find package version")
    return match.group(1)


def get_long_description():
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
        "Upstream": "https://github.com/yaronzz/Tidal-Media-Downloader",
    },

    packages=find_packages(),
    include_package_data=False,
    platforms="any",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Console",
        "Environment :: X11 Applications :: Qt",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: Multimedia :: Sound/Audio",
    ],
    keywords="tidal music downloader cli gui",
    python_requires=">=3.10",
    install_requires=["aigpy>=2022.7.8.1",
                      "requests>=2.22.0",
                      "pycryptodome",
                      "pydub",
                      "prettytable",
                      "lxml"],
    extras_require={
        "gui": ["PySide6>=6.5"],
    },
    entry_points={'console_scripts': [
        'tidekeeper = tidal_dl:main',
        'tidal-dl = tidal_dl:main',
        'tidekeeper-gui = tidal_dl.gui_app.__main__:main',
    ]}
)
