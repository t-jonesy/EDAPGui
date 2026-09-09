"""
File: linux_capture.py

Description:
  Linux (X11 / XWayland) replacement for the win32gui window lookup and mss screen grabs.

  Elite Dangerous under Proton is an X11 client, so even on a Wayland desktop the game window
  is reachable through XWayland (DISPLAY=:0). We grab pixels straight from that window with
  XShmGetImage, which is fast enough for the control loops (a few ms for a region, ~10-20 ms
  for a full 4K frame) and works in rootless XWayland where root-window grabs return garbage.

  Window discovery uses the window title 'Elite - Dangerous (CLIENT)'.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import os
import threading
import typing

import numpy as np
from Xlib import X, display, Xatom
from Xlib.error import XError

from EDlogger import logger

ED_WINDOW_TITLE = "Elite - Dangerous (CLIENT)"

# ---------------------------------------------------------------------------------------------
# Window discovery (python-xlib)
# ---------------------------------------------------------------------------------------------
_disp_lock = threading.Lock()
_disp: display.Display | None = None


def _get_display() -> display.Display:
    global _disp
    with _disp_lock:
        if _disp is None:
            _disp = display.Display(os.environ.get("DISPLAY", ":0"))
    return _disp


def _window_title(w) -> str | None:
    try:
        name = w.get_full_property(_get_display().intern_atom('_NET_WM_NAME'), 0)
        if name and name.value:
            v = name.value
            return v.decode('utf-8', 'replace') if isinstance(v, bytes) else str(v)
        n = w.get_wm_name()
        if isinstance(n, bytes):
            n = n.decode('utf-8', 'replace')
        return n
    except XError:
        return None


def find_window(title: str = ED_WINDOW_TITLE):
    """ Returns the Xlib Window object for the first mapped window with the given title, or None. """
    d = _get_display()
    root = d.screen().root

    def walk(w, depth=0):
        try:
            children = w.query_tree().children
        except XError:
            return None
        for c in children:
            try:
                t = _window_title(c)
                if t == title:
                    attrs = c.get_attributes()
                    if attrs.map_state == X.IsViewable:
                        return c
                r = walk(c, depth + 1)
                if r is not None:
                    return r
            except XError:
                continue
        return None

    return walk(root)


def window_rect(title: str = ED_WINDOW_TITLE) -> typing.Tuple[int, int, int, int] | None:
    """ (left, top, right, bottom) of the window in root coordinates, or None. """
    w = find_window(title)
    if w is None:
        return None
    try:
        g = w.get_geometry()
        root = _get_display().screen().root
        tr = w.translate_coords(root, 0, 0)
        # translate_coords gives coords of (0,0) of w in root space (negated)
        x, y = -tr.x, -tr.y
        return x, y, x + g.width, y + g.height
    except XError:
        return None


def window_exists(title: str = ED_WINDOW_TITLE) -> bool:
    return find_window(title) is not None


def focus_window(title: str = ED_WINDOW_TITLE):
    """ Best effort: ask the window manager to activate the window. Under Wayland compositors
    focus stealing may be blocked; the game normally already has focus when EDAP is used. """
    w = find_window(title)
    if w is None:
        return
    d = _get_display()
    try:
        from Xlib import protocol
        ev = protocol.event.ClientMessage(
            window=w, client_type=d.intern_atom('_NET_ACTIVE_WINDOW'),
            data=(32, [1, X.CurrentTime, 0, 0, 0]))
        d.screen().root.send_event(ev, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
        d.flush()
    except XError:
        pass


# ---------------------------------------------------------------------------------------------
# XShm capture (ctypes against libX11 / libXext)
# ---------------------------------------------------------------------------------------------
class _XImage(ctypes.Structure):
    _fields_ = [
        ("width", ctypes.c_int), ("height", ctypes.c_int), ("xoffset", ctypes.c_int),
        ("format", ctypes.c_int), ("data", ctypes.c_void_p), ("byte_order", ctypes.c_int),
        ("bitmap_unit", ctypes.c_int), ("bitmap_bit_order", ctypes.c_int), ("bitmap_pad", ctypes.c_int),
        ("depth", ctypes.c_int), ("bytes_per_line", ctypes.c_int), ("bits_per_pixel", ctypes.c_int),
        ("red_mask", ctypes.c_ulong), ("green_mask", ctypes.c_ulong), ("blue_mask", ctypes.c_ulong),
        ("obdata", ctypes.c_void_p),
        # struct funcs f; (6 function pointers)
        ("f0", ctypes.c_void_p), ("f1", ctypes.c_void_p), ("f2", ctypes.c_void_p),
        ("f3", ctypes.c_void_p), ("f4", ctypes.c_void_p), ("f5", ctypes.c_void_p),
    ]


class _XShmSegmentInfo(ctypes.Structure):
    _fields_ = [("shmseg", ctypes.c_ulong), ("shmid", ctypes.c_int),
                ("shmaddr", ctypes.c_void_p), ("readOnly", ctypes.c_int)]


IPC_PRIVATE = 0
IPC_CREAT = 0o1000
IPC_RMID = 0
ZPixmap = 2
AllPlanes = 0xFFFFFFFF


class XShmGrabber:
    """ Grabs regions of an X window into numpy BGRA arrays using MIT-SHM. Not thread safe;
    callers serialise through the lock. """

    def __init__(self, window_id: int, width: int, height: int):
        self.lock = threading.Lock()
        self._x11 = ctypes.CDLL(ctypes.util.find_library("X11") or "libX11.so.6")
        self._xext = ctypes.CDLL(ctypes.util.find_library("Xext") or "libXext.so.6")
        self._libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6")

        x11, xext, libc = self._x11, self._xext, self._libc
        x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x11.XDefaultScreen.argtypes = [ctypes.c_void_p]
        x11.XDefaultVisual.restype = ctypes.c_void_p
        x11.XDefaultVisual.argtypes = [ctypes.c_void_p, ctypes.c_int]
        x11.XDefaultDepth.argtypes = [ctypes.c_void_p, ctypes.c_int]
        x11.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        x11.XDestroyImage = None  # macro; we free via XFree of the struct below
        x11.XFree.argtypes = [ctypes.c_void_p]
        xext.XShmCreateImage.restype = ctypes.POINTER(_XImage)
        xext.XShmCreateImage.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_int,
                                         ctypes.c_void_p, ctypes.POINTER(_XShmSegmentInfo),
                                         ctypes.c_uint, ctypes.c_uint]
        xext.XShmAttach.argtypes = [ctypes.c_void_p, ctypes.POINTER(_XShmSegmentInfo)]
        xext.XShmDetach.argtypes = [ctypes.c_void_p, ctypes.POINTER(_XShmSegmentInfo)]
        xext.XShmGetImage.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(_XImage),
                                      ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
        xext.XShmGetImage.restype = ctypes.c_int
        libc.shmget.argtypes = [ctypes.c_int, ctypes.c_size_t, ctypes.c_int]
        libc.shmat.restype = ctypes.c_void_p
        libc.shmat.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
        libc.shmdt.argtypes = [ctypes.c_void_p]
        libc.shmctl.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p]

        self.dpy = x11.XOpenDisplay(os.environ.get("DISPLAY", ":0").encode())
        if not self.dpy:
            raise RuntimeError("XOpenDisplay failed")
        scr = x11.XDefaultScreen(self.dpy)
        visual = x11.XDefaultVisual(self.dpy, scr)
        depth = x11.XDefaultDepth(self.dpy, scr)

        self.window = window_id
        self.width, self.height = width, height
        self.shminfo = _XShmSegmentInfo()
        self.img = xext.XShmCreateImage(self.dpy, visual, depth, ZPixmap, None,
                                        ctypes.byref(self.shminfo), width, height)
        if not self.img:
            raise RuntimeError("XShmCreateImage failed")
        size = self.img.contents.bytes_per_line * self.img.contents.height
        self.shminfo.shmid = libc.shmget(IPC_PRIVATE, size, IPC_CREAT | 0o777)
        if self.shminfo.shmid < 0:
            raise RuntimeError("shmget failed")
        self.shminfo.shmaddr = libc.shmat(self.shminfo.shmid, None, 0)
        self.img.contents.data = self.shminfo.shmaddr
        self.shminfo.readOnly = 0
        if not xext.XShmAttach(self.dpy, ctypes.byref(self.shminfo)):
            raise RuntimeError("XShmAttach failed")
        x11.XSync(self.dpy, 0)
        # Mark for removal once detached; the mapping stays valid until shmdt.
        libc.shmctl(self.shminfo.shmid, IPC_RMID, None)
        self._buf = (ctypes.c_uint8 * size).from_address(self.shminfo.shmaddr)
        self._bpl = self.img.contents.bytes_per_line
        self._bpp = self.img.contents.bits_per_pixel // 8
        logger.debug(f"XShmGrabber ready: {width}x{height} depth={depth} bpp={self._bpp * 8}")

    def grab(self, x: int, y: int, w: int, h: int) -> np.ndarray | None:
        """ Grab a region (window coordinates). Returns a BGRA uint8 array (h, w, 4) or None. """
        if w <= 0 or h <= 0:
            return None
        x = max(0, x)
        y = max(0, y)
        w = min(w, self.width - x)
        h = min(h, self.height - y)
        if w <= 0 or h <= 0:
            return None
        with self.lock:
            # Reuse the full-size shm image but only request the sub-rectangle by temporarily
            # changing the image dimensions. The server packs rows at the requested width, so
            # bytes_per_line must follow the width.
            bpl = w * self._bpp
            self.img.contents.width = w
            self.img.contents.height = h
            self.img.contents.bytes_per_line = bpl
            ok = self._xext.XShmGetImage(self.dpy, self.window, self.img, x, y, AllPlanes)
            if not ok:
                return None
            arr = np.frombuffer(self._buf, dtype=np.uint8, count=bpl * h)
            return arr.reshape(h, w, self._bpp).copy()

    def close(self):
        try:
            self._xext.XShmDetach(self.dpy, ctypes.byref(self.shminfo))
            self._libc.shmdt(self.shminfo.shmaddr)
            self._x11.XFree(self.img)
        except Exception:
            pass


if __name__ == "__main__":
    import time
    import cv2
    r = window_rect()
    print("ED window rect:", r)
    if r:
        w = find_window()
        g = XShmGrabber(w.id, r[2] - r[0], r[3] - r[1])
        t = time.time()
        for _ in range(10):
            img = g.grab(0, 0, r[2] - r[0], r[3] - r[1])
        print("full frame avg %.1f ms" % ((time.time() - t) * 100))
        t = time.time()
        for _ in range(50):
            sub = g.grab(100, 100, 400, 300)
        print("region avg %.2f ms" % ((time.time() - t) * 20))
        cv2.imwrite("/tmp/edcap_xshm.png", cv2.cvtColor(img, cv2.COLOR_BGRA2BGR))
        print("wrote /tmp/edcap_xshm.png", img.shape)
