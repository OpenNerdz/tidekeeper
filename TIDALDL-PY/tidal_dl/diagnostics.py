#!/usr/bin/env python
# -*- encoding: utf-8 -*-
import os
import shutil
import tempfile
from .runtime import print
import sys

import aigpy

from . import apiKey
from .printf import Printf
from .settings import SETTINGS, TOKEN
from .tidal import TIDAL_API


def _statusLine(status, name, detail):
    suffix = f" - {detail}" if detail else ""
    return f"[{status}] {name}{suffix}"


def _printStatus(status, name, detail=""):
    line = _statusLine(status, name, detail)
    if status == "OK":
        Printf.success(line)
    elif status == "WARN":
        Printf.info(line)
    else:
        Printf.err(line)


def _checkDownloadPath():
    path = SETTINGS.downloadPath or "."
    try:
        os.makedirs(path, exist_ok=True)
        with tempfile.TemporaryFile(mode="w", encoding="utf-8", dir=path) as output:
            output.write("ok")
            output.flush()
        return "OK", "Download path", os.path.abspath(path)
    except Exception as e:
        return "ERR", "Download path", str(e)


def _checkApiKey():
    if apiKey.isItemValid(SETTINGS.apiKeyIndex):
        item = apiKey.getItem(SETTINGS.apiKeyIndex)
        return "OK", "TIDAL client", item.get("platform", str(SETTINGS.apiKeyIndex))
    return "ERR", "TIDAL client", f"invalid client index {SETTINGS.apiKeyIndex}"


def _checkFfmpeg():
    path = shutil.which("ffmpeg")
    if path:
        return "OK", "ffmpeg", path
    return (
        "WARN",
        "ffmpeg",
        "not found; install ffmpeg for video downloads and optional FLAC remux",
    )


def _checkToken():
    if aigpy.string.isNull(TOKEN.accessToken):
        return "WARN", "Token", "not logged in"

    try:
        if TIDAL_API.verifyAccessToken(TOKEN.accessToken):
            return "OK", "Token", f"valid for country {TOKEN.countryCode or 'unknown'}"
        if not aigpy.string.isNull(TOKEN.refreshToken):
            return "WARN", "Token", "access token expired; refresh token is present"
        return "ERR", "Token", "access token expired and no refresh token is saved"
    except Exception as e:
        return "ERR", "Token", str(e)


def runDoctor():
    print("Tidekeeper doctor")
    if sys.platform.startswith("win"):
        Printf.info(
            "Platform: Windows - check folder permissions, long paths, antivirus blocking, "
            "and protected directories if downloads fail."
        )
    checks = [
        _checkDownloadPath(),
        _checkApiKey(),
        _checkFfmpeg(),
        _checkToken(),
    ]

    hasError = False
    for status, name, detail in checks:
        _printStatus(status, name, detail)
        if status == "ERR":
            hasError = True

    if hasError:
        Printf.err("Doctor found issues that should be fixed.")
        return False

    Printf.success("Doctor finished.")
    return True
