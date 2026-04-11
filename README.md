# TVM

TVM is a small Tkinter-based virtual macropad for Linux/X11. It lets you click a target window and send configured commands to it.

## Features
- Button-driven command launcher
- Per-user config at `~/.config/tvm/config.py`
- X11 window selection
- Terminal launch and detached app launch

## Install

```bash
python3 -m pip install .


NOTE:

TVM needs an X11/libxdo Python binding. On many systems one of these works:

python3 -m pip install xdo

or

python3 -m pip install python-libxdo-ng

You may also need your distro's libxdo package.

Build and install it:

cd tvm
python3 -m pip install --upgrade build
python3 -m build
python3 -m pip install .
