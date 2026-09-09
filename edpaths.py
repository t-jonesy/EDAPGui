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
from os import environ, listdir
from os.path import expanduser, getmtime, isdir, join

ED_STEAM_APPID = "359320"
IS_WINDOWS = sys.platform == "win32"

_DEFAULT_PREFIXES = [
    "~/.local/share/Steam/steamapps/compatdata/{appid}/pfx",
    "~/.steam/steam/steamapps/compatdata/{appid}/pfx",
    "~/.var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/compatdata/{appid}/pfx",
]


def _candidate_prefixes() -> list[str]:
    """ All existing Proton prefixes that could belong to Elite Dangerous, in no particular
    order. The game may be installed in one Steam library while a different library's
    compatdata holds the live prefix, so we consider every candidate and let the caller pick. """
    cands = [expanduser(c.format(appid=ED_STEAM_APPID)) for c in _DEFAULT_PREFIXES]
    # Steam libraries from libraryfolders.vdf (there is one per install location)
    for vdf in (expanduser("~/.local/share/Steam/steamapps/libraryfolders.vdf"),
                expanduser("~/.steam/steam/steamapps/libraryfolders.vdf")):
        try:
            with open(vdf, "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('"path"'):
                        lib = line.split('"')[3]
                        cands.append(join(lib, "steamapps", "compatdata", ED_STEAM_APPID, "pfx"))
        except OSError:
            pass
    # De-duplicate, keep only existing dirs
    seen = set()
    out = []
    for c in cands:
        if c not in seen and isdir(c):
            seen.add(c)
            out.append(c)
    return out


def _prefix_freshness(prefix: str) -> float:
    """ Newest mtime among a prefix's *.binds and Journal.*.log files. Higher = more likely the
    live prefix the game is actually reading and writing. Returns 0.0 if nothing found. """
    import glob
    newest = 0.0
    base = join(prefix, "drive_c", "users", "steamuser")
    patterns = [
        join(base, "AppData", "Local", "Frontier Developments", "Elite Dangerous",
             "Options", "Bindings", "*.binds"),
        join(base, "Saved Games", "Frontier Developments", "Elite Dangerous", "Journal.*.log"),
        join(base, "Saved Games", "Frontier Developments", "Elite Dangerous", "Status.json"),
    ]
    for pat in patterns:
        for f in glob.glob(pat):
            try:
                newest = max(newest, getmtime(f))
            except OSError:
                pass
    return newest


def _newest_binds_mtime(prefix: str) -> float:
    """ Newest mtime among a prefix's Options/Bindings/*.binds files, or 0.0 if none. """
    import glob
    newest = 0.0
    pat = join(prefix, "drive_c", "users", "steamuser", "AppData", "Local",
               "Frontier Developments", "Elite Dangerous", "Options", "Bindings", "*.binds")
    for f in glob.glob(pat):
        try:
            newest = max(newest, getmtime(f))
        except OSError:
            pass
    return newest


def _prefix_from_running_game() -> str | None:
    """ If Elite Dangerous is running, return the Proton prefix it was launched with, read from
    the process environment (STEAM_COMPAT_DATA_PATH/WINEPREFIX). This is authoritative: it is the
    exact prefix the live game reads its bindings from. Linux only; returns None if not found. """
    proc = "/proc"
    if not isdir(proc):
        return None
    try:
        pids = [d for d in listdir(proc) if d.isdigit()]
    except OSError:
        return None
    for pid in pids:
        try:
            with open(join(proc, pid, "cmdline"), "rb") as f:
                cmd = f.read()
        except OSError:
            continue
        if b"EliteDangerous64.exe" not in cmd and b"/%s/" % ED_STEAM_APPID.encode() not in cmd:
            continue
        try:
            with open(join(proc, pid, "environ"), "rb") as f:
                raw = f.read()
        except OSError:
            continue
        env = {}
        for item in raw.split(b"\0"):
            if b"=" in item:
                k, _, v = item.partition(b"=")
                env[k.decode("utf-8", "replace")] = v.decode("utf-8", "replace")
        cdp = env.get("STEAM_COMPAT_DATA_PATH")
        if cdp:
            pfx = join(cdp, "pfx")
            if isdir(pfx):
                return pfx
        wp = env.get("WINEPREFIX")
        if wp and isdir(wp):
            return wp
    return None


def _find_proton_prefix() -> str | None:
    p = environ.get("EDAP_ED_PREFIX")
    if p:
        return expanduser(p)
    # 1. The running game's own prefix is authoritative (handles the case where the game is
    #    installed in one library but its live compatdata is elsewhere).
    running = _prefix_from_running_game()
    if running:
        return running
    cands = _candidate_prefixes()
    if not cands:
        return None
    # 2. Rank by the newest *.binds file specifically. The Saved Games/journal folder can be a
    #    symlink shared between prefixes, so journal/Status mtimes tie and cannot disambiguate
    #    which prefix owns the bindings; the binds files are per-prefix and do.
    with_binds = [(c, _newest_binds_mtime(c)) for c in cands]
    with_binds = [(c, m) for c, m in with_binds if m > 0.0]
    if with_binds:
        return max(with_binds, key=lambda t: t[1])[0]
    # 3. Last resort: newest journal/Status, else the first existing prefix.
    best = max(cands, key=_prefix_freshness)
    if _prefix_freshness(best) > 0.0:
        return best
    return cands[0]


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
