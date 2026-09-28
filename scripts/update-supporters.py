"""Validate paginated GitHub stargazers and update the bundled snapshot."""

import argparse
import json
import os
import re
import tempfile
from pathlib import Path


def update_supporters(pages, target):
    if not isinstance(pages, list) or not pages:
        raise ValueError("Expected at least one page of GitHub stargazers")
    names = {}
    for page in pages:
        if not isinstance(page, list):
            raise ValueError("Each GitHub page must be a list")
        for account in page:
            login = account.get("login") if isinstance(account, dict) else None
            if not isinstance(login, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", login):
                raise ValueError("Invalid GitHub login in stargazer response")
            names.setdefault(login.casefold(), login)
    content = json.dumps([names[key] for key in sorted(names)], indent=2) + "\n"
    if target.exists() and target.read_text(encoding="utf-8") == content:
        return False
    # Never replace a valid snapshot with a partial response or partial write.
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(content)
            handle.close()
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("response", type=Path, help="JSON pages from gh api --paginate --slurp")
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    pages = json.loads(args.response.read_text(encoding="utf-8"))
    changed = update_supporters(pages, args.target)
    print("Updated supporter snapshot" if changed else "Supporter snapshot is unchanged")


if __name__ == "__main__":
    main()
