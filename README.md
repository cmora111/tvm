Requirements:

```
```
# TVM

https://github.com/cmora111/tvm

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

or

git://github.com/rshk/python-libxdo

or

You may also need your distro's libxdo package.

Build and install it:

cd tvm
python3 -m pip install --upgrade build
python3 -m build
python3 -m pip install .

An example configuration file ***src/tvm_config.py***:
```
debug = { "Flag": "False" }

# For other linux terminals (Ubuntu)
terminal = { "application": "gnome-terminal" }
# For raspberryy pi)
#terminal = { "application": "lxterminal" }

Categories = {
    "Select Window": {
        "Select window": [0, "None"]
    },
    "Admin_CMDs":  {
        "ps": [1, "ps axwwl"],
        "psa": [2, "ps axwwl|grep -i <name>"],
        "ls": [2, "ls <name>"],
        "cd": [2, "cd <name>"],
        "find_grep": [2, "find . -type f -exec grep -i <name> {} \; -print"],
    },
    "APT_CMDs": {
        "Update": [2, "sudo apt update"],
        "Upgrade": [2, "sudo apt upgrade -y"],
        "Install": [2, "sudo apt install <name>"],
        "Reinstall": [2, "sudo apt install -y --reinstall <name>"],
        "Purge": [2, "sudo apt purge -y <name>"],
        "Autoremove": [2, "sudo apt autoremove -y"],
        "Fix-Broken": [2, "sudo apt --fix-broken install -y"]
    },
    "Applications": {
        "Glances": [1, "glances"],
        "Firefox": [3, "firefox &"],
        "Wireshark": [3, "sudo /usr/bin/wireshark  &"]
    },
    # You can issue vi commands
    "Vi": {
        "Write_Exit": [2, ":wq!\^M"],
        "NoWrite_Exit": [2, ":q\^M"],
        "Reload": [2, ":e!\^M"],
        "Date_Stamp": [2, "!!date\^M"]
    }
}

##Main Screen:

![Example Main Screen](docs/main.png "Example Main Screen")

##Main Screen and Admin_CMDs Screen:

![Example Main Screen and Admin Commands](docs/main_and_Admin_CMDs.png "Example Main Screen and Admin  Commands")

##Main Screen and APT_CMDs Screen:

![Example Main Screen and APT Commands](docs/main_and_APT_CMDs.png "Example Main Screen and APT  Commands")

##Main Screen and Applications Screen:

![Example Main Screen and Aplications](docs/main_and_Aplications.png "Example Main Screen and Aplications")

##Main Screen and Vi Commands:

![Example Main Screen and Vi Commands](docs/main_and_Vi_CMDs.png "Example Main Screen and Vi Commands")

