"""Reject release tags that do not match the package and changelog, without imports."""

import argparse
import re
from pathlib import Path


def check_release(root, ref):
    if not ref.startswith("refs/tags/"):
        return "Branch build: no release will be published."

    tag = ref.removeprefix("refs/tags/")
    if not re.fullmatch(r"v[0-9]{4}\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", tag):
        raise ValueError("Release tags must use vYYYY.M.D.N without leading zeroes")

    source = (root / "TIDALDL-PY/tidal_dl/printf.py").read_text(encoding="utf-8")
    match = re.search(r"^VERSION\s*=\s*['\"]([^'\"]+)['\"]", source, re.MULTILINE)
    if match is None:
        raise ValueError("Unable to find the package VERSION")
    version = match.group(1)
    if tag != f"v{version}":
        raise ValueError(f"Tag {tag} does not match package version {version}")

    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    if not re.search(rf"^## {re.escape(version)}(?: - [^\n]+)?\s*$", changelog, re.MULTILINE):
        raise ValueError(f"CHANGELOG.md has no release section for {version}")
    return f"Release {tag}: package version and changelog agree."


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", required=True, help="Full Git ref, e.g. refs/tags/v2026.9.28.0")
    args = parser.parse_args()
    try:
        print(check_release(Path(__file__).resolve().parents[1], args.ref))
    except (OSError, ValueError) as error:
        parser.exit(1, f"Release validation failed: {error}\n")


if __name__ == "__main__":
    main()
