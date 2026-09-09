"""
File: edpaths.py

Description:
  Resolves the Elite Dangerous data directories in a platform-independent way.

  On Windows the game writes to:
    %LOCALAPPDATA%\\Frontier Developments\\Elite Dangerous\\...      (Options, Bindings, Graphics)
    <Saved Games>\\Frontier Developments\\Elite Dangerous\\...        (Journals, Status.json, ...)

  On Linux (Steam/Proton) those same paths live inside the Wine prefix:
    <compatdata>/359320/pfx/drive_c/users/steamuser/AppData/Local/Frontier Developments/Elite Dangerous
    <compatdata>/359320/pfx/drive_c/users/steamuser/Saved Games/Frontier Developments/Elite Dangerous

  Overrides (environment variables, all optional):
    EDAP_ED_PREFIX        Path to the Proton prefix ('.../compatdata/359320/pfx').
    EDAP_ED_LOCALAPPDATA  Path to the 'Elite Dangerous' folder under AppData/Local.
    EDAP_ED_SAVEDGAMES    Path to the 'Elite Dangerous' folder under Saved Games.
    EDAP_ED_BINDINGS_FILE Explicit .binds file to use instead of the latest in Options/Bindings.
"""
from __future__ import annotations

import os
import sys
from os import environ
from os.path import expanduser, isdir, join

ED_STEAM_APPID = "359320"
IS_WINDOWS = sys.platform == "win32"

_DEFAULT_PREFIXES = [
    "~/.local/share/Steam/steamapps/compatdata/{appid}/pfx",
    "~/.steam/steam/steamapps/compatdata/{appid}/pfx",
    "~/.var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/compatdata/{appid}/pfx",
]


def _find_proton_prefix() -> str | None:
    p = environ.get("EDAP_ED_PREFIX")
    if p:
        return expanduser(p)
    for cand in _DEFAULT_PREFIXES:
        cand = expanduser(cand.format(appid=ED_STEAM_APPID))
        if isdir(cand):
            return cand
    # Look through additional Steam libraries listed in libraryfolders.vdf
    vdf = expanduser("~/.local/share/Steam/steamapps/libraryfolders.vdf")
    try:
        with open(vdf, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith('"path"'):
                    lib = line.split('"')[3]
                    cand = join(lib, "steamapps", "compatdata", ED_STEAM_APPID, "pfx")
                    if isdir(cand):
                        return cand
    except OSError:
        pass
    return None


def local_appdata_dir() -> str:
    """ The 'Elite Dangerous' folder under AppData/Local (holds Options/Bindings, Options/Graphics...). """
    p = environ.get("EDAP_ED_LOCALAPPDATA")
    if p:
        return expanduser(p)
    if IS_WINDOWS:
        return join(environ["LOCALAPPDATA"], "Frontier Developments", "Elite Dangerous")
    prefix = _find_proton_prefix()
    if prefix is None:
        return "./linux_ed/AppData"
    return join(prefix, "drive_c", "users", "steamuser", "AppData", "Local",
                "Frontier Developments", "Elite Dangerous")


def saved_games_dir() -> str:
    """ The 'Elite Dangerous' folder under Saved Games (holds Journal.*.log, Status.json, ...). """
    p = environ.get("EDAP_ED_SAVEDGAMES")
    if p:
        return expanduser(p)
    if IS_WINDOWS:
        from WindowsKnownPaths import get_path, FOLDERID, UserHandle
        return join(get_path(FOLDERID.SavedGames, UserHandle.current), "Frontier Developments", "Elite Dangerous")
    prefix = _find_proton_prefix()
    if prefix is None:
        return "./linux_ed"
    return join(prefix, "drive_c", "users", "steamuser", "Saved Games",
                "Frontier Developments", "Elite Dangerous")


def bindings_dir() -> str:
    return join(local_appdata_dir(), "Options", "Bindings")


def graphics_dir() -> str:
    return join(local_appdata_dir(), "Options", "Graphics")


def player_dir() -> str:
    return join(local_appdata_dir(), "Options", "Player")


def saved_games_file(name: str) -> str:
    return join(saved_games_dir(), name)


def _steam_library_dirs() -> list[str]:
    libs = [expanduser("~/.local/share/Steam"), expanduser("~/.steam/steam")]
    for vdf in (expanduser("~/.local/share/Steam/steamapps/libraryfolders.vdf"),
                expanduser("~/.steam/steam/steamapps/libraryfolders.vdf")):
        try:
            with open(vdf, "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('"path"'):
                        libs.append(line.split('"')[3])
        except OSError:
            pass
    return [l for i, l in enumerate(libs) if l not in libs[:i]]


def control_schemes_dir() -> str | None:
    """ The game's built-in ControlSchemes folder (holds the preset *.binds files), or None. """
    p = environ.get("EDAP_ED_CONTROLSCHEMES")
    if p:
        return expanduser(p)
    if IS_WINDOWS:
        return None
    for lib in _steam_library_dirs():
        for product in ("elite-dangerous-odyssey-64", "elite-dangerous-64", "FORC-FDEV-DO-1000"):
            cand = join(lib, "steamapps", "common", "Elite Dangerous", "Products", product, "ControlSchemes")
            if isdir(cand):
                return cand
    return None


if __name__ == "__main__":
    print("local appdata:", local_appdata_dir())
    print("saved games  :", saved_games_dir())
    print("bindings     :", bindings_dir())
