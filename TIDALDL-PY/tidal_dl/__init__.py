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
from .runtime import configure_logging, print
import sys
import os
import getopt
import aigpy

from . import apiKey
from .events import (
    changeApiKey, changePathSettings, changeQualitySettings, changeSettings,
    loginByAccessToken, loginByConfig, loginByWeb, logout, start,
)
from .lang.language import LANG
from .settings import SETTINGS, TOKEN
from .tidal import TIDAL_API
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

SHORT_OPTIONS = "hvgl:o:q:r:c:"
LONG_OPTIONS = [
    "help", "version", "gui", "doctor", "update", "update-gui", "paths", "open-output",
    "video-only", "videos-only", "link=", "output=", "quality=", "quality-priority=",
    "resolution=", "configPathOverride=",
]


def _command_options():
    opts, args = getopt.getopt(sys.argv[1:], SHORT_OPTIONS, LONG_OPTIONS)
    if args:
        raise ValueError("Unexpected argument: " + args[0] + ". Use --link for a URL or file")
    return opts


def preMainCommand():
    for opt, val in _command_options():
        if opt in ('-c', '--configPathOverride'):
            val = os.path.expanduser(val)
            if not os.path.isdir(val):
                raise ValueError("configPathOverride must be an existing directory")
            PATHS.homePathOverride = val


def _command_settings(opts):
    """Validate all options before changing or saving any profile values."""
    from .enums import VideoQuality
    values = {}
    for opt, val in opts:
        if opt in ('-o', '--output'):
            if not val.strip() or '\x00' in val:
                raise ValueError('Output folder must be a nonempty path')
            values['downloadPath'] = os.path.expanduser(val)
        elif opt in ('-q', '--quality'):
            quality = SETTINGS.getAudioQualityOrNone(val)
            if quality is None:
                raise ValueError('Unknown audio quality: ' + val)
            values.update(audioQuality=quality, audioQualityPriority=[])
        elif opt == '--quality-priority':
            entries = val.split(',')
            if not entries or any(SETTINGS.getAudioQualityOrNone(item) is None for item in entries):
                raise ValueError('Quality priority must contain valid, comma-separated qualities')
            priority = SETTINGS.getAudioQualityPriority(entries)
            values.update(audioQuality=priority[0], audioQualityPriority=priority)
        elif opt in ('-r', '--resolution'):
            normalized = val.strip().upper()
            if not any(normalized in (item.name, str(item.value), str(item.value) + 'P') for item in VideoQuality):
                raise ValueError('Unknown video resolution: ' + val)
            values['videoQuality'] = SETTINGS.getVideoQuality(normalized)
    return values


def mainCommand():
    """Return an exit code for a command, or None to open the menu."""
    try:
        opts = _command_options()
        if any(opt in ('-h', '--help') for opt, _ in opts):
            Printf.usage()
            return 0
        if any(opt in ('-v', '--version') for opt, _ in opts):
            Printf.logo()
            return 0
        values = _command_settings(opts)
        if values:
            previous = dict(SETTINGS.__dict__)
            try:
                SETTINGS.__dict__.update(values)
                SETTINGS.save()
            except OSError:
                SETTINGS.__dict__.clear()
                SETTINGS.__dict__.update(previous)
                raise
    except (getopt.GetoptError, ValueError, OSError) as error:
        Printf.err(str(error) + ". Use 'tidekeeper -h' for usage.")
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
    try:
        return _main()
    except KeyboardInterrupt:
        Printf.info('Cancelled. Partial transfers are kept for retry.')
        return 130
    except EOFError:
        return 0
    except OSError as error:
        Printf.err(str(error))
        return 1


def _main():
    if len(sys.argv) > 1:
        try:
            opts = _command_options()
            if any(opt in ('-h', '--help', '-v', '--version') for opt, _ in opts):
                return mainCommand()
            _command_settings(opts)
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
    TIDAL_API.clearSavedSessionIfClientChanged()

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
