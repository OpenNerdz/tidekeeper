#!/usr/bin/env python
# -*- encoding: utf-8 -*-

import os


TERMUX_PREFIX = "/com.termux/files/usr"
TERMUX_HOME = "/com.termux/files/home"


def isTermux(environ=None):
    environ = os.environ if environ is None else environ
    prefix = environ.get("PREFIX", "")
    home = environ.get("HOME", "")
    return (
        "TERMUX_VERSION" in environ
        or TERMUX_PREFIX in prefix
        or TERMUX_HOME in home
    )


def getTermuxDownloadPath(environ=None):
    environ = os.environ if environ is None else environ
    if environ.get("TIDEKEEPER_DOWNLOAD_PATH"):
        return environ["TIDEKEEPER_DOWNLOAD_PATH"]

    # Shared storage is only usable after termux-setup-storage has run.
    external_storage = environ.get("EXTERNAL_STORAGE")
    if external_storage and os.path.isdir(os.path.join(external_storage, "Download")):
        return os.path.join(external_storage, "Download", "Tidekeeper")

    home = environ.get("HOME")
    if home:
        return os.path.join(home, "downloads", "Tidekeeper")
    return "./download/"


def getDefaultDownloadPath(environ=None):
    environ = os.environ if environ is None else environ
    if environ.get("TIDEKEEPER_DOWNLOAD_PATH"):
        return environ["TIDEKEEPER_DOWNLOAD_PATH"]
    if isTermux(environ):
        return getTermuxDownloadPath(environ)
    return "./download/"
