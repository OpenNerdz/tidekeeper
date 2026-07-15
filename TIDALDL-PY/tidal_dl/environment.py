#!/usr/bin/env python
# -*- encoding: utf-8 -*-

import os


TERMUX_PREFIX = "/com.termux/files/usr"
TERMUX_HOME = "/com.termux/files/home"


def isTermux(environ=None):
    environ = environ or os.environ
    prefix = environ.get("PREFIX", "")
    home = environ.get("HOME", "")
    return (
        "TERMUX_VERSION" in environ
        or TERMUX_PREFIX in prefix
        or TERMUX_HOME in home
    )


def getTermuxDownloadPath(environ=None):
    environ = environ or os.environ
    if environ.get("TIDEKEEPER_DOWNLOAD_PATH"):
        return environ["TIDEKEEPER_DOWNLOAD_PATH"]

    candidates = []
    home = environ.get("HOME")
    external_storage = environ.get("EXTERNAL_STORAGE")
    if external_storage:
        candidates.append(os.path.join(external_storage, "Download", "Tidekeeper"))

    for candidate in candidates:
        if os.path.isdir(os.path.dirname(candidate)):
            return candidate

    if home:
        return os.path.join(home, "downloads", "Tidekeeper")
    return "./download/"


def getDefaultDownloadPath(environ=None):
    if isTermux(environ):
        return getTermuxDownloadPath(environ)
    return "./download/"
