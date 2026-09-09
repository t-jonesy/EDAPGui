"""
File: linux_input.py

Description:
  Linux replacement for the Windows SendInput based key/mouse injection.
  Creates a virtual keyboard and a virtual absolute-pointer via /dev/uinput (python-evdev).
  The compositor (KWin/Wayland, X11, gamescope) sees these as real input devices, so the
  events reach Proton/Wine games the same way a physical keyboard would.

  Requirements: read/write access to /dev/uinput (udev uaccess ACL, or membership of the
  'input' group).

  Key codes: the game bindings are expressed as DirectInput scan codes (see directinput.SCANCODE).
  For the main keyboard block (1..88) DirectInput scan codes are identical to Linux KEY_* codes.
  Extended keys (0x80 and above) need an explicit translation which is provided by DI_TO_LINUX.
"""
from __future__ import annotations

import threading
import time

from evdev import UInput, ecodes as e, AbsInfo

from EDlogger import logger

# DirectInput scan code -> Linux input event code for keys outside the 1..88 range.
DI_TO_LINUX = {
    86: e.KEY_102ND,           # Key_BackSlash duplicate (ISO <> key)
    115: e.KEY_RO,             # Key_ABNT_C1
    126: e.KEY_KPCOMMA,        # Key_ABNT_C2
    144: e.KEY_PREVIOUSSONG,
    153: e.KEY_NEXTSONG,
    156: e.KEY_KPENTER,
    157: e.KEY_RIGHTCTRL,
    160: e.KEY_MUTE,
    161: e.KEY_CALC,
    162: e.KEY_PLAYPAUSE,
    164: e.KEY_STOPCD,
    174: e.KEY_VOLUMEDOWN,
    176: e.KEY_VOLUMEUP,
    178: e.KEY_HOMEPAGE,
    181: e.KEY_KPSLASH,
    183: e.KEY_SYSRQ,
    184: e.KEY_RIGHTALT,
    197: e.KEY_PAUSE,
    199: e.KEY_HOME,
    200: e.KEY_UP,
    201: e.KEY_PAGEUP,
    203: e.KEY_LEFT,
    205: e.KEY_RIGHT,
    207: e.KEY_END,
    208: e.KEY_DOWN,
    209: e.KEY_PAGEDOWN,
    210: e.KEY_INSERT,
    211: e.KEY_DELETE,
    219: e.KEY_LEFTMETA,
    220: e.KEY_RIGHTMETA,
    221: e.KEY_COMPOSE,        # Key_Apps
    222: e.KEY_POWER,
    223: e.KEY_SLEEP,
    227: e.KEY_WAKEUP,
    229: e.KEY_SEARCH,
    230: e.KEY_BOOKMARKS,
    231: e.KEY_REFRESH,
    232: e.KEY_STOP,
    233: e.KEY_FORWARD,
    234: e.KEY_BACK,
    235: e.KEY_COMPUTER,
    236: e.KEY_MAIL,
    237: e.KEY_MEDIA,
}


def di_to_linux(scancode: int) -> int | None:
    if 1 <= scancode <= 88:
        return scancode
    return DI_TO_LINUX.get(scancode)


# Characters -> (DirectInput scan code, shift) for typing free text (galaxy map search etc.)
_CHAR_TO_DI = {}
for _i, _c in enumerate("1234567890"):
    _CHAR_TO_DI[_c] = (2 + _i, False)
for _c, _s in zip("!@#$%^&*()", "1234567890"):
    _CHAR_TO_DI[_c] = (_CHAR_TO_DI[_s][0], True)
_row1 = "qwertyuiop"
_row2 = "asdfghjkl"
_row3 = "zxcvbnm"
for _i, _c in enumerate(_row1):
    _CHAR_TO_DI[_c] = (16 + _i, False)
for _i, _c in enumerate(_row2):
    _CHAR_TO_DI[_c] = (30 + _i, False)
for _i, _c in enumerate(_row3):
    _CHAR_TO_DI[_c] = (44 + _i, False)
for _c in _row1 + _row2 + _row3:
    _CHAR_TO_DI[_c.upper()] = (_CHAR_TO_DI[_c][0], True)
_CHAR_TO_DI.update({
    ' ': (57, False), '-': (12, False), '_': (12, True), '=': (13, False), '+': (13, True),
    '[': (26, False), '{': (26, True), ']': (27, False), '}': (27, True),
    ';': (39, False), ':': (39, True), "'": (40, False), '"': (40, True),
    '`': (41, False), '~': (41, True), '\\': (43, False), '|': (43, True),
    ',': (51, False), '<': (51, True), '.': (52, False), '>': (52, True),
    '/': (53, False), '?': (53, True), '\n': (28, False), '\t': (15, False),
})


class VirtualKeyboard:
    """ A uinput keyboard exposing every key code we could possibly send. """

    def __init__(self, name="EDAP Virtual Keyboard"):
        keys = set(range(1, 89)) | set(DI_TO_LINUX.values())
        self._lock = threading.Lock()
        self._ui = UInput({e.EV_KEY: sorted(keys)}, name=name, version=0x1)
        # Give the compositor a moment to pick up the new device before the first key press.
        time.sleep(0.5)
        logger.info(f"Created uinput keyboard '{name}'.")

    def key(self, scancode: int, down: bool):
        code = di_to_linux(scancode)
        if code is None:
            logger.warning(f"No Linux key code for DirectInput scan code {scancode}.")
            return
        with self._lock:
            self._ui.write(e.EV_KEY, code, 1 if down else 0)
            self._ui.syn()

    def type_string(self, text: str, interval: float = 0.05):
        """ Type free text character by character (US layout). """
        for ch in text:
            m = _CHAR_TO_DI.get(ch)
            if m is None:
                logger.warning(f"type_string: no key mapping for {ch!r}, skipped.")
                continue
            sc, shift = m
            if shift:
                self.key(42, True)
                time.sleep(0.01)
            self.key(sc, True)
            time.sleep(0.03)
            self.key(sc, False)
            if shift:
                time.sleep(0.01)
                self.key(42, False)
            time.sleep(interval)

    def close(self):
        try:
            self._ui.close()
        except Exception:
            pass


class VirtualPointer:
    """ A uinput absolute pointer (tablet style) so we can click at screen coordinates. """

    RANGE = 65535

    def __init__(self, name="EDAP Virtual Pointer"):
        self._ui = UInput({
            e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE, e.BTN_TOOL_PEN, e.BTN_TOUCH],
            e.EV_ABS: [
                (e.ABS_X, AbsInfo(value=0, min=0, max=self.RANGE, fuzz=0, flat=0, resolution=0)),
                (e.ABS_Y, AbsInfo(value=0, min=0, max=self.RANGE, fuzz=0, flat=0, resolution=0)),
            ],
        }, name=name, version=0x1)
        time.sleep(0.5)
        self.screen_w = 1920
        self.screen_h = 1080
        logger.info(f"Created uinput pointer '{name}'.")

    def set_screen_size(self, w: int, h: int):
        self.screen_w, self.screen_h = w, h

    def move(self, x: int, y: int):
        ax = int(max(0, min(self.RANGE, x * self.RANGE / max(1, self.screen_w - 1))))
        ay = int(max(0, min(self.RANGE, y * self.RANGE / max(1, self.screen_h - 1))))
        self._ui.write(e.EV_ABS, e.ABS_X, ax)
        self._ui.write(e.EV_ABS, e.ABS_Y, ay)
        self._ui.syn()

    def button(self, btn: int, down: bool):
        self._ui.write(e.EV_KEY, btn, 1 if down else 0)
        self._ui.syn()

    def click(self, x: int, y: int, delay: float = 0.1):
        self.move(x, y)
        time.sleep(0.05)
        self.button(e.BTN_LEFT, True)
        time.sleep(delay)
        self.button(e.BTN_LEFT, False)

    def close(self):
        try:
            self._ui.close()
        except Exception:
            pass


_keyboard: VirtualKeyboard | None = None
_pointer: VirtualPointer | None = None
_init_lock = threading.Lock()


def keyboard() -> VirtualKeyboard:
    global _keyboard
    with _init_lock:
        if _keyboard is None:
            _keyboard = VirtualKeyboard()
    return _keyboard


def pointer() -> VirtualPointer:
    global _pointer
    with _init_lock:
        if _pointer is None:
            _pointer = VirtualPointer()
    return _pointer


if __name__ == "__main__":
    kb = keyboard()
    print("Typing 'hello' in 3s, switch to a text field...")
    time.sleep(3)
    kb.type_string("Hello EDAP\n")
