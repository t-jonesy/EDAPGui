# Running EDAPGui on Linux (Steam / Proton)

EDAPGui was written for Windows. This fork adds a Linux backend so it can drive Elite Dangerous
running under Steam/Proton on an X11 or Wayland desktop (tested on CachyOS, KDE Plasma Wayland,
4K borderless, Proton-CachyOS).

## How it works

| Windows (upstream)                  | Linux (this fork)                                             |
|-------------------------------------|---------------------------------------------------------------|
| `win32gui` window lookup            | `linux_capture.py` – finds the `Elite - Dangerous (CLIENT)` X11/XWayland window |
| `mss` monitor screen grab           | `linux_capture.XShmGrabber` – MIT-SHM grab of the game window (~20 ms for a 4K frame) |
| `SendInput` DirectInput scan codes  | `linux_input.py` – virtual keyboard/pointer via `/dev/uinput` (evdev) |
| `keyboard` global hotkeys           | `linux_hotkeys.py` – X11 passive key grabs (`XGrabKey`)       |
| `pyautogui.typewrite`               | `linux_input.VirtualKeyboard.type_string`                     |
| `pynput` mouse                      | uinput absolute pointer (`MousePt.py`)                        |
| win32 GDI overlay                   | `linux_overlay.py` – no-op stub (nothing drawn)               |
| `%LOCALAPPDATA%` / Saved Games      | `edpaths.py` – resolves the Proton prefix                     |

Proton games are X11 clients, so on a Wayland desktop everything goes through XWayland
(`DISPLAY=:0`). Because DirectInput scan codes 1–88 are identical to Linux `KEY_*` codes the
game bindings translate 1:1; extended keys (arrows, Home/End, keypad Enter, …) are mapped in
`linux_input.DI_TO_LINUX`.

## Requirements

* Python 3.12 (managed by [uv](https://docs.astral.sh/uv/); 3.14 is too new for paddle/torch).
* Read/write access to `/dev/uinput`. Most desktop distros grant this to the logged-in seat via
  a udev `uaccess` rule; otherwise add your user to the `input` group (or a udev rule).
* `libX11`, `libXext` (present on any desktop).
* `espeak-ng` for voice output (optional).
* Elite Dangerous in **Borderless** or windowed mode (the default Proton setup). Exclusive
  fullscreen is not needed and not tested.

## Install / run

```sh
git clone https://github.com/t-jonesy/EDAPGui.git
cd EDAPGui
./start_ed_ap.sh          # creates .venv with uv, installs requirements-linux.txt, starts the GUI
```

Run `./start_ed_ap.sh` from a terminal in the same graphical session as the game (or set
`DISPLAY`/`XAUTHORITY` when starting it from ssh).

## Paths

`edpaths.py` looks for the Proton prefix in the usual Steam locations
(`~/.local/share/Steam/steamapps/compatdata/359320/pfx`, other libraries listed in
`libraryfolders.vdf`). Override with environment variables when needed:

| Variable                  | Meaning                                                    |
|---------------------------|------------------------------------------------------------|
| `EDAP_ED_PREFIX`          | Proton prefix (`.../compatdata/359320/pfx`)                |
| `EDAP_ED_LOCALAPPDATA`    | `.../AppData/Local/Frontier Developments/Elite Dangerous`  |
| `EDAP_ED_SAVEDGAMES`      | `.../Saved Games/Frontier Developments/Elite Dangerous`    |
| `EDAP_ED_BINDINGS_FILE`   | Explicit `.binds` file to use                              |
| `EDAP_ED_CONTROLSCHEMES`  | The game's `ControlSchemes` folder (built-in presets)      |

Run `python edpaths.py` inside the venv to print what was detected.

## Key bindings

EDAP reads the game's keyboard bindings from `Options/Bindings/*.binds`. That folder only
exists once you have changed at least one binding in-game. Until then this fork falls back to
the built-in preset from the game's `ControlSchemes` folder (`KeyboardMouseOnly.binds` unless
`StartPreset.start` says otherwise) and logs a warning. Many autopilot actions need keyboard
binds that the presets leave empty, so do set them up in-game per the main readme; the game
then writes `Custom.4.x.binds`, which takes precedence automatically.

## Known gaps

* No on-screen overlay (the Windows version draws debug rectangles/text over the game).
* Window focus stealing (`ActivateEliteEachKey`) is best effort under Wayland; keep the game
  focused while an assist is running.
* Global hotkeys only fire while an X11/XWayland window (e.g. the game) has focus.
* MangoHud or other overlays drawn into the game window are captured too; disable them if
  they overlap regions EDAP inspects (top-left of the screen).
* Screen scale for 3840x2160 is set to 1.5 (height ratio to the 3440x1440 templates); run the
  Calibration tab if template matches are poor.
