#!/usr/bin/env python
# -*- encoding: utf-8 -*-
'''
@File    :   __init__.py
@Time    :   2020/11/08
@Author  :   Yaronzz
@Version :   3.0
@Contact :   yaronhuang@foxmail.com
@Desc    :
'''
from .runtime import configure_logging, print, check_cancelled, DownloadCancelled, sleep as cancellable_sleep
import sys
import os
import getopt
import aigpy

from .events import *
from .settings import *
from .diagnostics import runDoctor
from .paths import PATHS, openPath
from .printf import Printf
from .updater import run_update


def startGui():
    import importlib

    try:
        gui_module = importlib.import_module("tidal_dl.gui_app.__main__")
    except ImportError:
        Printf.err("GUI is not bundled with this executable. Run tidekeeper-gui or install tidekeeper[gui].")
        return 1
    return gui_module.main()

def preMainCommand():
    preArgs = []
    previousArg = ""
    for arg in sys.argv[1:]:
        if (arg.startswith('--configPathOverride=') or arg.startswith('-c')
                or arg == "--configPathOverride" or previousArg in ('-c', '--configPathOverride')):
            preArgs.append(arg)
        previousArg = arg

    opts, args = getopt.getopt(preArgs, "c:", ["configPathOverride="])
    for opt, val in opts:
        if opt in ('-c', '--configPathOverride'):
            if not os.path.isdir(val):
                raise ValueError("configPathOverride must be an existing directory")
            PATHS.homePathOverride = val

def mainCommand():
    """Parse CLI flags.

    Returns:
        int exit code when the CLI handled the request and should exit
        None when the interactive menu should start
    """
    try:
        opts, args = getopt.getopt(sys.argv[1:],
                                   "hvgl:o:q:r:c:",
                                   [
                                       "help", "version", "gui", "doctor",
                                       "update", "update-gui",
                                       "paths", "open-output",
                                       "video-only", "videos-only",
                                       "link=", "output=", "quality=", "quality-priority=",
                                       "resolution=", "configPathOverride=",
                                   ])
    except getopt.GetoptError as errmsg:
        Printf.err(vars(errmsg)['msg'] + ". Use 'tidekeeper -h' for usage.")
        return 1

    link = None
    showGui = False
    showDoctor = False
    updateInstall = False
    updateGuiInstall = False
    showPaths = False
    openOutput = False
    videoOnly = False

    for opt, val in opts:
        if opt in ('-h', '--help'):
            Printf.usage()
            return 0
        if opt in ('-v', '--version'):
            Printf.logo()
            return 0
        if opt in ('-g', '--gui'):
            showGui = True
            continue
        if opt == '--doctor':
            showDoctor = True
            continue
        if opt == '--paths':
            showPaths = True
            continue
        if opt == '--open-output':
            openOutput = True
            continue
        if opt in ('--video-only', '--videos-only'):
            videoOnly = True
            continue
        if opt == '--update':
            updateInstall = True
            continue
        if opt == '--update-gui':
            updateInstall = True
            updateGuiInstall = True
            continue
        if opt in ('-l', '--link'):
            link = val
            continue
        if opt in ('-o', '--output'):
            SETTINGS.downloadPath = val
            SETTINGS.save()
            continue
        if opt in ('-q', '--quality'):
            SETTINGS.audioQuality = SETTINGS.getAudioQuality(val)
            SETTINGS.audioQualityPriority = []
            SETTINGS.save()
            continue
        if opt in ('--quality-priority',):
            SETTINGS.audioQualityPriority = SETTINGS.getAudioQualityPriority(val)
            if SETTINGS.audioQualityPriority:
                SETTINGS.audioQuality = SETTINGS.audioQualityPriority[0]
            SETTINGS.save()
            continue
        if opt in ('-r', '--resolution'):
            SETTINGS.videoQuality = SETTINGS.getVideoQuality(val)
            SETTINGS.save()
            continue

    if showDoctor:
        return 0 if runDoctor() else 1

    if showPaths:
        Printf.paths()
        return 0

    if openOutput:
        try:
            opened = openPath(SETTINGS.downloadPath)
            Printf.success("Opened download folder: " + opened)
            return 0
        except OSError as exc:
            Printf.err("Could not open download folder: " + str(exc))
            return 1

    if updateInstall:
        return 0 if updateTidekeeper(updateGuiInstall) else 1

    if not aigpy.path.mkdirs(SETTINGS.downloadPath):
        Printf.err(LANG.select.MSG_PATH_ERR + SETTINGS.downloadPath)
        return 1

    if showGui:
        result = startGui()
        return result if isinstance(result, int) else 0

    if link is not None:
        if not loginByConfig() and not loginByWeb():
            return 1
        Printf.info(LANG.select.SETTING_DOWNLOAD_PATH + ':' + SETTINGS.downloadPath)
        return 0 if start(link, videoOnly) else 1
    return None


def normalizeChoice(choice):
    aliases = {
        "": "",
        "q": "0",
        "quit": "0",
        "exit": "0",
        "login": "1",
        "signin": "1",
        "sign-in": "1",
        "refresh": "1",
        "logout": "2",
        "signout": "2",
        "sign-out": "2",
        "token": "3",
        "access-token": "3",
        "path": "4",
        "paths": "4",
        "folder": "4",
        "quality": "5",
        "options": "6",
        "settings": "6",
        "client": "7",
        "apikey": "7",
        "api-key": "7",
        "show": "8",
        "status": "8",
        "help": "8",
        "all": "8",
        "update": "9",
        "upgrade": "9",
        "clear": "clear",
        "cls": "clear",
    }
    clean = choice.strip()
    return aliases.get(clean.lower(), clean)


def updateTidekeeper(include_gui=False):
    Printf.info("Updating Tidekeeper...")
    result = run_update(include_gui)
    if result.command:
        Printf.info("Command: " + " ".join(result.command))
    if result.output.strip():
        print(result.output.strip())
    if result.ok:
        Printf.success(result.message)
    elif result.standalone:
        Printf.info(result.message)
    else:
        Printf.err(result.message)
    return result.ok


def main():
    if len(sys.argv) > 1:
        try:
            preMainCommand()
        except (getopt.GetoptError, ValueError) as exc:
            Printf.err(str(exc) + ". Use 'tidekeeper -h' for usage.")
            return 1

    configure_logging(PATHS.getLogPath())
    SETTINGS.read(PATHS.getProfilePath())
    TOKEN.read(PATHS.getTokenPath())
    if not apiKey.isItemValid(SETTINGS.apiKeyIndex):
        SETTINGS.apiKeyIndex = apiKey.getDefaultIndex()
        SETTINGS.save()
    TIDAL_API.apiKey = apiKey.getItem(SETTINGS.apiKeyIndex)

    if len(sys.argv) > 1:
        exit_code = mainCommand()
        if exit_code is not None:
            return exit_code

    if not loginByConfig():
        loginByWeb()

    Printf.checkVersion()

    while True:
        Printf.choices()
        choice = normalizeChoice(Printf.enter("Paste URL or choice > "))
        if choice == "":
            continue
        if choice == "clear":
            Printf.clearScreen()
            continue
        if choice == "0":
            return 0
        elif choice == "1":
            if not loginByConfig():
                loginByWeb()
        elif choice == "2":
            logout()
        elif choice == "3":
            loginByAccessToken()
        elif choice == "4":
            changePathSettings()
        elif choice == "5":
            changeQualitySettings()
        elif choice == "6":
            changeSettings()
        elif choice == "7":
            if changeApiKey():
                loginByWeb()
        elif choice == "8":
            Printf.settings()
        elif choice == "9":
            updateTidekeeper(False)
        else:
            start(choice)


if __name__ == '__main__':
    main()
