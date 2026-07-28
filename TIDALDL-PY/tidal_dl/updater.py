#!/usr/bin/env python
# -*- encoding: utf-8 -*-
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass


PROJECT_URL = "https://github.com/OpenNerdz/tidekeeper"
RELEASES_URL = f"{PROJECT_URL}/releases/latest"
PACKAGE_URL = "git+https://github.com/OpenNerdz/tidekeeper.git#subdirectory=TIDALDL-PY"


@dataclass
class UpdateResult:
    ok: bool
    command: list[str]
    output: str
    standalone: bool = False

    @property
    def message(self) -> str:
        if self.standalone:
            return (
                "Standalone builds cannot safely replace the running executable. "
                f"Download the latest Tidekeeper asset from {RELEASES_URL}"
            )
        if self.ok:
            return "Tidekeeper update completed. Restart Tidekeeper to use the updated version."
        return "Tidekeeper update failed."


def is_standalone_build() -> bool:
    return bool(getattr(sys, "frozen", False))


def update_target(include_gui: bool = False) -> str:
    package_name = "tidekeeper[gui]" if include_gui else "tidekeeper"
    return f"{package_name} @ {PACKAGE_URL}"


def update_command(include_gui: bool = False) -> list[str]:
    return [sys.executable, "-m", "pip", "install", "--upgrade", update_target(include_gui)]


def run_update(include_gui: bool = False) -> UpdateResult:
    if is_standalone_build():
        return UpdateResult(False, [], "", standalone=True)

    command = update_command(include_gui)
    env = os.environ.copy()
    env.setdefault("PIP_DISABLE_PIP_VERSION_CHECK", "1")
    try:
        process = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            check=False,
        )
    except OSError as exc:
        return UpdateResult(False, command, str(exc))
    return UpdateResult(process.returncode == 0, command, process.stdout or "")
