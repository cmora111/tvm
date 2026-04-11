# TVM

TVM is a small Tkinter-based virtual macropad for Linux/X11. It lets you click a target window and send configured commands to it.

Repository: `https://github.com/cmora111/tvm`

## Features

- Button-driven command launcher
- Per-user config at `~/.config/tvm/config.py`
- X11 window selection through `xdo`
- Terminal launch and detached app launch
- Isolated `xdo` helper subprocess to reduce whole-app crashes from native libxdo failures
- Debug logging to `~/.config/tvm/tvm.log`

## Platform support

TVM is currently aimed at:

- Ubuntu/Linux
- Xorg / X11 sessions
- Python 3.10+

Wayland is not a supported target at this time.

## Categories

```text
Development Status :: 3 - Alpha
Environment :: X11 Applications
Intended Audience :: Developers
License :: OSI Approved :: MIT License
Operating System :: POSIX :: Linux
Programming Language :: Python :: 3
Topic :: Desktop Environment
Topic :: System :: Shells
Topic :: Utilities
```

## Why the stability patch exists

The original app called `Xdo()` directly from the Tkinter process for both window selection and command sending. If `python-libxdo` or the underlying native `libxdo` layer crashes, the whole GUI process can die. The updated design moves those calls into `tvm.xdo_helper`, a small helper subprocess.

That means:

- native `xdo` failures are easier to detect
- timeouts are explicit
- the Tkinter UI is more likely to stay alive
- failed sends can clear the stale selected window and ask for reselection

## Install

### Install from source

```bash
python3 -m pip install .
```

### Install X11/libxdo binding

TVM needs both:

1. a Python `xdo` binding
2. the system `libxdo` package

One common Ubuntu flow is:

```bash
sudo apt update
sudo apt install -y libxdo-dev
python3 -m pip install xdo
```

If that specific binding does not work on your system, other bindings may also work, but the package must still provide:

- `from xdo import Xdo`
- `select_window_with_click()`
- `focus_window()`
- `enter_text_window()`
- `send_keysequence_window()`

## Build and install a wheel

```bash
python3 -m pip install --upgrade build
python3 -m build
python3 -m pip install .
```

## Example configuration

TVM uses a per-user config file at:

```text
~/.config/tvm/config.py
```

Example:

```python
debug = {"Flag": False}

terminal = {
    "application": "gnome-terminal"
}

Categories = {
    "Select Window": {
        "Select window": [0, "None"]
    },
    "Admin_CMDs": {
        "ls": [2, "ls"],
        "ps": [2, "ps axwwl"],
        "pwd": [2, "pwd"],
        "cd": [2, "cd "],
    },
    "APT_CMDs": {
        "Update": [2, "sudo apt update"],
        "Upgrade": [2, "sudo apt upgrade -y"],
        "Install": [2, "sudo apt install "],
        "Reinstall": [2, "sudo apt install -y --reinstall "],
        "Purge": [2, "sudo apt purge -y "],
        "Autoremove": [2, "sudo apt autoremove -y"],
        "Fix-Broken": [2, "sudo apt --fix-broken install -y"]
    },
    "Applications": {
        "htop": [1, "htop"],
        "Firefox": [3, "firefox > /dev/null 2>&1 &"],
        "Visual": [3, "code > /dev/null 2>&1 &"]
    },
    "Vi": {
        "Write_Exit": [2, ":wq!\\r"],
        "NoWrite_Exit": [2, ":q\\r"],
        "Reload": [2, ":e!\\r"],
        "Date_Stamp": [2, "!!date\\r"]
    }
}
```

## Command types

TVM command entries use the form:

```python
[label] = [command_type, command_string]
```

Where `command_type` is:

```text
0 = select a target window
1 = spawn a terminal and run the command there
2 = send the command to the currently selected window
3 = run detached in the background
```

## Debugging

Set debug on in your config:

```python
debug = {"Flag": True}
```

Then inspect:

```bash
cat ~/.config/tvm/tvm.log
```

That log is useful for:

- helper launch failures
- empty helper responses
- stale window problems
- command send attempts

## Stability notes

The patched app now does the following when sending commands:

- requires a selected target window
- logs the target window ID and command
- routes the native X11 work through a subprocess helper
- clears the stored window ID if sending fails
- asks the user to reselect the window after a failure

## Packaging note

The stability patch adds this new module to the package:

```text
src/tvm/xdo_helper.py
```

Be sure that file is included in the repo before building or publishing.

## Screenshots

### Main Screen

![Example Main Screen](docs/main.png "Example Main Screen")

### Main Screen and Admin Commands

![Example Main Screen and Admin Commands](docs/main_and_Admin_CMDs.png "Example Main Screen and Admin Commands")

### Main Screen and APT Commands

![Example Main Screen and APT Commands](docs/main_and_APT_CMDs.png "Example Main Screen and APT Commands")

### Main Screen and Applications

![Example Main Screen and Applications](docs/main_and_Aplications.png "Example Main Screen and Applications")

### Main Screen and Vi Commands

![Example Main Screen and Vi Commands](docs/main_and_Vi_CMDs.png "Example Main Screen and Vi Commands")
