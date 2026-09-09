#!/usr/bin/env bash
# EDAPGui start script for Linux.
# Creates a Python 3.12 virtual environment with uv (https://docs.astral.sh/uv/) on first run,
# installs requirements-linux.txt and starts the GUI.
#
# Requirements:
#   - Elite Dangerous running under Steam/Proton (any X11 or Wayland desktop; the game is
#     reached through XWayland on Wayland sessions).
#   - Read/write access to /dev/uinput for the virtual keyboard (udev uaccess rule or the
#     'input' group).
#   - espeak-ng for voice output (optional).
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
    if ! command -v uv >/dev/null 2>&1; then
        echo "uv not found. Install it (e.g. 'pacman -S uv' or https://docs.astral.sh/uv/)." >&2
        exit 1
    fi
    echo "Creating virtual environment (.venv) with Python 3.12..."
    uv venv --python 3.12 .venv
    echo "Installing requirements..."
    uv pip install --python .venv/bin/python -r requirements-linux.txt --index-strategy unsafe-best-match
fi

export DISPLAY="${DISPLAY:-:0}"
exec .venv/bin/python EDAPGui.py "$@"
