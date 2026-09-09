"""
File: linux_overlay.py

Description:
  No-op stand-in for the win32 GDI Overlay used on Windows. Keeps the same API so ED_AP can
  call it unconditionally; nothing is drawn on screen. The stored items are kept so a real
  overlay (e.g. a transparent Tk/Qt window) can be dropped in later.
"""
from __future__ import annotations

from datetime import datetime
from copy import copy

from Screen_Regions import Quad


class Vector:
    def __init__(self, x, y, w, h):
        self.x = x
        self.y = y
        self.w = w
        self.h = h

    def __ne__(self, other):
        return (self.x + self.y + self.w + self.h) != (other.x + other.y + other.w + other.h)


class Overlay:
    def __init__(self, parent_window, elite=0):
        self.parent = parent_window
        self.targetRect = Vector(0, 0, 1920, 1200)
        self.lines = {}
        self.quadrilaterals = {}
        self.text = {}
        self.floating_text = {}
        self.fnt = ["Times New Roman", 12, 12]
        self.pos = [0, 0]
        try:
            import linux_capture
            r = linux_capture.window_rect()
            if r:
                self.targetRect = Vector(r[0], r[1], r[2] - r[0], r[3] - r[1])
        except Exception:
            pass

    def overlay_rect(self, key, pt1, pt2, color, thick, duration: float = 3.0):
        self.lines[key] = [pt1, pt2, color, thick, duration, datetime.now()]

    def overlay_rect1(self, key, rect, color, thick, duration: float = 3.0):
        self.lines[key] = [(rect[0], rect[1]), (rect[2], rect[3]), color, thick, duration, datetime.now()]

    def overlay_quad_pct(self, key, quad: Quad, color, thick, duration: float = 3.0):
        q = copy(quad)
        q.scale_from_origin(self.targetRect.w, self.targetRect.h)
        self.quadrilaterals[key] = [q, color, thick, duration, datetime.now()]

    def overlay_quad_pix(self, key, quad: Quad, color, thick, duration: float = 3.0):
        self.quadrilaterals[key] = [quad, color, thick, duration, datetime.now()]

    def overlay_setfont(self, fontname, fsize):
        self.fnt = [fontname, fsize, fsize]

    def overlay_set_pos(self, x, y):
        self.pos = [x, y]

    def overlay_text(self, key, txt, row, col, color, duration: float = 3.0):
        self.text[key] = [txt, row, col, color, duration, datetime.now()]

    def overlay_floating_text(self, key, txt, x, y, color, duration: float = 3.0):
        self.floating_text[key] = [txt, x, y, color, duration, datetime.now()]

    def overlay_paint(self):
        pass

    def overlay_clear(self):
        self.lines.clear()
        self.quadrilaterals.clear()
        self.text.clear()
        self.floating_text.clear()

    def overlay_remove_rect(self, key):
        self.lines.pop(key, None)

    def overlay_remove_quad(self, key):
        self.quadrilaterals.pop(key, None)

    def overlay_remove_text(self, key):
        self.text.pop(key, None)

    def overlay_remove_floating_text(self, key):
        self.floating_text.pop(key, None)

    def overlay_quit(self):
        pass
