# TVM — Terminal Virtual Macropad

TVM is a lightweight **Tkinter-based command launcher** for Linux (Xorg) that lets you send commands directly to any terminal window or spawn new ones.

It acts like a **virtual macropad for your terminal**, with support for:

* window targeting
* command categories
* placeholder prompts
* confirmation dialogs
* plugin system

---

## ✨ Features

* 🖱️ Select any X11 window as a command target
* ⌨️ Send commands directly into an existing terminal
* 🧩 Plugin system with hot reload
* 🧠 Smart placeholders like `<path>`, `<user>`, `<host>`
* 🔐 Optional confirmation for dangerous commands
* 📂 Organized categories and subcommands
* 📊 Status bar feedback
* 🧪 Designed for rapid iteration and customization

---

## 📦 Installation

### Option 1 — Development (recommended)

```bash
git clone https://github.com/cmora111/tvm
cd tvm
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Run:

```bash
python -m tvm
# or
tvm
```

---

### Option 2 — Without install (quick run)

```bash
PYTHONPATH=src python -m tvm
```

---

## 🧰 Requirements

* Linux (Xorg session)
* Python 3.10+
* `xdotool`
* `xwininfo`

Install dependencies:

```bash
sudo apt install xdotool x11-utils
```

---

## 🚀 Usage

### 1. Select a target window

Click:

```
Select Window → Select window
```

Then click any terminal.

---

### 2. Run commands

Example categories:

```
Admin_CMDs → ls
Admin_CMDs → pwd
Admin_CMDs → cd
```

Commands are sent directly to the selected terminal.

---

## 🧠 Placeholders

Commands can include placeholders:

```bash
cd <path>
ssh <user>@<host>
```

TVM will prompt you for each value before execution.

---

## 🔐 Confirmation

Add confirmation for risky commands:

```python
'Danger Upgrade': [2, 'sudo apt upgrade -y', {'confirm': True}]
```

You’ll get a popup before execution.

---

## ⚙️ Configuration

Config file location:

```bash
~/.config/tvm/config.py
```

Example:

```python
debug = {'Flag': False}

terminal = {'application': 'gnome-terminal'}

Categories = {
    'Select Window': {
        'Select window': [0, 'None'],
    },

    'Admin_CMDs': {
        'ls': [2, 'ls'],
        'cd': [2, 'cd <path>'],
        'ssh': [2, 'ssh <user>@<host>'],
        'Danger Upgrade': [2, 'sudo apt upgrade -y', {'confirm': True}],
    },

    'Applications': {
        'htop': [1, 'htop'],
        'VS Code': [3, 'code > /dev/null 2>&1 &'],
    },

    'Plugins': {
        'Hello World Plugin': ['plugin', 'hello_world'],
    },
}
```

---

## 🧩 Command Types

```text
0 → Select window
1 → Spawn new terminal
2 → Send to selected window
3 → Run detached command
'plugin' → Run plugin
```

---

## 🔌 Plugins

Plugins live in:

```bash
~/.config/tvm/plugins/
```

Example plugin:

```python
PLUGIN_NAME = "Hello World"
PLUGIN_VERSION = "1.0.0"
TVM_PLUGIN_API_VERSION = 1

def run(app, context):
    app.send_text_to_window('echo "Hello from plugin!"')
```

Reload plugins inside the app.

---

## 🖥️ UI Overview

Main window:

* Category buttons
* Window selector
* Plugin tools
* Status bar

Category window:

* Command buttons
* Stays open for repeated use

---

## ⚠️ Notes

* Works only on **Xorg**, not Wayland
* Window activation depends on your window manager
* Some terminals may block synthetic input

---

## 🛠️ Development

Project layout:

```text
src/tvm/
├── app.py
├── cli.py
├── xdo_helper.py
├── default_config.py
```

Run in dev mode:

```bash
pip install -e .
```

---

## 🧼 Cleanup

See:

```
CLEANUP.md
```

---

## 📌 Roadmap

* Multi-field form UI for placeholders
* Command search
* Favorites / pinned commands
* Config editor UI
* Profiles (multiple configs)
* Command history
* Plugin permissions system

---

## 📄 License

MIT License

---

## 🙌 Author

Carlos Mora
https://github.com/cmora111

---

## ⭐ Contributing

Pull requests welcome.
Ideas, plugins, and improvements are encouraged.

