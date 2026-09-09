import sys
from time import sleep

"""
File:MousePt.py

Description:
  Class to handles getting x,y location for a mouse click, and a routine to click on a x, y location

Author: sumzer0@yahoo.com
"""

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    from pynput.mouse import *


    class MousePoint:
        def __init__(self):
            self.x = 0
            self.y = 0
            self.term = False

            self.ls = None # Listener(on_move=self.on_move, on_click=self.on_click, on_scroll=self.on_scroll)
            self.ms = Controller()

        def on_move(self, x, y):
            return True

        def on_scroll(self, x, y, dx, dy):
            return True

        def on_click(self, x, y, button, pressed):
            self.x = x
            self.y = y
            self.term = True
            return True

        def get_location(self):
            self.term = False
            self.x = 0
            self.y = 0
            self.ls  = Listener(on_move=self.on_move, on_click=self.on_click, on_scroll=self.on_scroll)
            self.ls.start()

            try:
                while self.term == False:
                    sleep(0.5)
            except:
                pass

            self.ls.stop()

            return self.x, self.y

        def do_click(self, x, y, delay = 0.1):
            # position the mouse and do left click, duration in seconds
            self.ms.position=(x, y)

            self.ms.press(Button.left)
            sleep(delay)
            self.ms.release(Button.left)

else:
    class MousePoint:
        """ Linux implementation: clicks go through a uinput absolute pointer; get_location polls
        the X pointer (works while an X11/XWayland window such as the game has the pointer). """
        def __init__(self):
            self.x = 0
            self.y = 0
            self.term = False
            self._ptr = None

        def _pointer(self):
            if self._ptr is None:
                import linux_input
                from linux_capture import _get_display
                self._ptr = linux_input.pointer()
                scr = _get_display().screen()
                self._ptr.set_screen_size(scr.width_in_pixels, scr.height_in_pixels)
            return self._ptr

        def get_location(self):
            from Xlib import X
            from linux_capture import _get_display
            root = _get_display().screen().root
            # Wait for a left button press, then report where it happened.
            pressed = False
            while True:
                p = root.query_pointer()
                if p.mask & X.Button1Mask:
                    pressed = True
                    self.x, self.y = p.root_x, p.root_y
                elif pressed:
                    return self.x, self.y
                sleep(0.02)

        def do_click(self, x, y, delay=0.1):
            self._pointer().click(int(x), int(y), delay)


def main():
    m = MousePoint()
    m.do_click(1977,510)


if __name__ == "__main__":
    main()
