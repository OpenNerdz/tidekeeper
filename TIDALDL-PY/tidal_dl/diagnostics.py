#!/usr/bin/env python
# -*- encoding: utf-8 -*-
import os
import shutil
import sys

import aigpy

from . import apiKey
from .printf import Printf
from .settings import SETTINGS, TOKEN
from .tidal import TIDAL_API


def __statusLine__(status, name, detail):
    suffix = f" - {detail}" if detail else ""
    return f"[{status}] {name}{suffix}"


def __printStatus__(status, name, detail=""):
    line = __statusLine__(status, name, detail)
    if status == "OK":
        Printf.success(line)
    elif status == "WARN":
        Printf.info(line)
    else:
        Printf.err(line)


def __checkDownloadPath__():
    path = SETTINGS.downloadPath or "."
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".tidekeeper-write-test")
        with open(probe, "w", encoding="utf-8") as output:
            output.write("ok")
        os.remove(probe)
        return "OK", "Download path", os.path.abspath(path)
    except Exception as e:
        return "ERR", "Download path", str(e)


def __checkApiKey__():
    if apiKey.isItemValid(SETTINGS.apiKeyIndex):
        item = apiKey.getItem(SETTINGS.apiKeyIndex)
        return "OK", "TIDAL client", item.get("platform", str(SETTINGS.apiKeyIndex))
    return "ERR", "TIDAL client", f"invalid client index {SETTINGS.apiKeyIndex}"


def __checkFfmpeg__():
    path = shutil.which("ffmpeg")
    if path:
        return "OK", "ffmpeg", path
    return "WARN", "ffmpeg", "not found; video handling or tagging may be limited"


def __checkToken__():
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
        Printf.info("Platform: Windows - common download issues: path permissions, long paths (>260 chars), antivirus blocking, or need to run terminal as normal user (not over-protected dirs).")
    checks = [
        __checkDownloadPath__(),
        __checkApiKey__(),
        __checkFfmpeg__(),
        __checkToken__(),
    ]

    hasError = False
    for status, name, detail in checks:
        __printStatus__(status, name, detail)
        if status == "ERR":
            hasError = True

    if hasError:
        Printf.err("Doctor found issues that should be fixed.")
        return False

    Printf.success("Doctor finished.")
    return True
