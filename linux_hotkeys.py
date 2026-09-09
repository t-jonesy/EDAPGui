"""
File: linux_hotkeys.py

Description:
  Minimal drop-in for the parts of the 'keyboard' package that EDAPGui uses
  (add_hotkey / remove_all_hotkeys), implemented with X11 passive key grabs.

  Because Elite Dangerous under Proton is an X11 client, a grab on the XWayland root window
  fires whenever the game (or any other X client) has keyboard focus, which is exactly when the
  autopilot hotkeys are wanted. It does not require root or membership of the 'input' group.
"""
from __future__ import annotations

import os
import threading

from Xlib import X, XK, display

from EDlogger import logger

# Names used in AP.json -> X keysym names
_NAMES = {
    'home': 'Home', 'end': 'End', 'ins': 'Insert', 'insert': 'Insert', 'del': 'Delete', 'delete': 'Delete',
    'pgup': 'Page_Up', 'page up': 'Page_Up', 'pageup': 'Page_Up',
    'pgdn': 'Page_Down', 'page down': 'Page_Down', 'pagedown': 'Page_Down',
    'up': 'Up', 'down': 'Down', 'left': 'Left', 'right': 'Right',
    'space': 'space', ' ': 'space', 'enter': 'Return', 'esc': 'Escape', 'escape': 'Escape',
    'tab': 'Tab', 'backspace': 'BackSpace', 'pause': 'Pause', 'scroll lock': 'Scroll_Lock',
    'print screen': 'Print',
}
_MODS = {'ctrl': X.ControlMask, 'control': X.ControlMask, 'alt': X.Mod1Mask, 'shift': X.ShiftMask,
         'win': X.Mod4Mask, 'super': X.Mod4Mask, 'windows': X.Mod4Mask}
_IGNORED_MODS = [0, X.LockMask, X.Mod2Mask, X.LockMask | X.Mod2Mask]  # CapsLock / NumLock variants


class _Hotkeys:
    def __init__(self):
        self._lock = threading.Lock()
        self._hotkeys: dict[tuple[int, int], tuple] = {}  # (keycode, mods) -> (callback, args)
        self._disp: display.Display | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    def _ensure_thread(self):
        if self._thread is not None:
            return
        self._disp = display.Display(os.environ.get("DISPLAY", ":0"))
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="LinuxHotkeys", daemon=True)
        self._thread.start()

    def _parse(self, combo: str) -> tuple[int, int] | None:
        parts = [p.strip().lower() for p in combo.split('+')] if combo != ' ' else [' ']
        mods = 0
        key = None
        for p in parts:
            if p in _MODS:
                mods |= _MODS[p]
            else:
                key = p
        if key is None:
            return None
        ksname = _NAMES.get(key)
        if ksname is None:
            if len(key) == 1:
                ksname = key
            else:
                ksname = key[0].upper() + key[1:]
        keysym = XK.string_to_keysym(ksname)
        if keysym == 0:
            logger.warning(f"Hotkey '{combo}': unknown key '{key}'.")
            return None
        keycode = self._disp.keysym_to_keycode(keysym)
        if keycode == 0:
            logger.warning(f"Hotkey '{combo}': no keycode for '{key}'.")
            return None
        return keycode, mods

    def add_hotkey(self, combo: str, callback, args=()):
        with self._lock:
            self._ensure_thread()
            parsed = self._parse(combo)
            if parsed is None:
                return
            keycode, mods = parsed
            root = self._disp.screen().root
            for extra in _IGNORED_MODS:
                try:
                    root.grab_key(keycode, mods | extra, 1, X.GrabModeAsync, X.GrabModeAsync)
                except Exception as ex:
                    logger.warning(f"grab_key failed for '{combo}': {ex}")
            self._disp.flush()
            self._hotkeys[(keycode, mods)] = (callback, tuple(args) if args is not None else ())
            logger.info(f"Registered hotkey '{combo}' (keycode {keycode}, mods {mods}).")

    def remove_all_hotkeys(self):
        with self._lock:
            if self._disp is None:
                return
            root = self._disp.screen().root
            for (keycode, mods) in list(self._hotkeys):
                for extra in _IGNORED_MODS:
                    try:
                        root.ungrab_key(keycode, mods | extra)
                    except Exception:
                        pass
            self._hotkeys.clear()
            self._disp.flush()

    def _loop(self):
        d = self._disp
        while self._running:
            try:
                ev = d.next_event()
            except Exception as ex:
                logger.error(f"Hotkey loop error: {ex}")
                break
            if ev.type != X.KeyPress:
                continue
            mods = ev.state & (X.ShiftMask | X.ControlMask | X.Mod1Mask | X.Mod4Mask)
            with self._lock:
                entry = self._hotkeys.get((ev.detail, mods))
            if entry is None:
                continue
            cb, args = entry
            try:
                cb(*args)
            except Exception as ex:
                logger.error(f"Hotkey callback error: {ex}")


_instance = _Hotkeys()


def add_hotkey(combo: str, callback, args=()):
    _instance.add_hotkey(combo, callback, args)


def remove_all_hotkeys():
    _instance.remove_all_hotkeys()


if __name__ == "__main__":
    import time
    add_hotkey('end', print, args=('END pressed',))
    add_hotkey('home', print, args=('HOME pressed',))
    print("Press Home / End (Ctrl+C to quit)")
    while True:
        time.sleep(1)
