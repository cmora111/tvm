# TVM — Terminal Virtual Macropad

TVM is a lightweight Tkinter-based macropad for Linux that sends commands to a selected terminal window.

It allows you to:

* Select any X11 window
* Send predefined commands
* Run scripts/macros quickly
* Extend behavior via plugins

---

## 🚀 Features

* GUI-based macropad
* Click-to-select target window
* Command execution via `xdotool`
* Configurable button grid
* Plugin system (extensible actions)
* Works on Ubuntu / Xorg

---

## ⚠️ Requirements

* Linux (Xorg session)
* Python 3.10+
* External tools:

  * `xdotool`
  * `x11-utils`

Install dependencies:

```bash
sudo apt install xdotool x11-utils
```

---

## 📦 Installation (Recommended)

Using pipx:

```bash
sudo apt install pipx
pipx ensurepath

pipx install tvm
```

Run:

```bash
tvm
```

---

## 🧪 Development Mode

```bash
git clone https://github.com/cmora111/tvm
cd tvm

pipx install -e .
```

Or without installing:

```bash
PYTHONPATH=src python3 -m tvm
```

---

## ⚙️ Configuration

TVM loads config from:

```text
~/.config/tvm/config.py
```

Create it from the example:

```bash
mkdir -p ~/.config/tvm
cp examples/config.py ~/.config/tvm/config.py
```

---

## 🧩 Plugin System

TVM supports plugins for custom actions.

### Plugin location:

```text
~/.config/tvm/plugins/
```

### Example plugin:

```python
# ~/.config/tvm/plugins/hello.py

def run(app, context):
    print("Hello from plugin!")
```

### Use in config:

```python
{
    "label": "Hello",
    "type": "plugin",
    "plugin": "hello"
}
```

---

## 🖥️ Desktop Integration

Create a launcher:

```bash
mkdir -p ~/.local/share/applications
nano ~/.local/share/applications/tvm.desktop
```

Paste:

```ini
[Desktop Entry]
Name=TVM
Comment=Terminal Virtual Macropad
Exec=tvm
Icon=utilities-terminal
Terminal=false
Type=Application
Categories=Utility;
```

Make executable:

```bash
chmod +x ~/.local/share/applications/tvm.desktop
```

Now TVM will appear in your app launcher.

---

## 📁 Project Structure

```text
tvm/
├── src/tvm/
│   ├── app.py
│   ├── cli.py
│   ├── xdo_helper.py
│   └── default_config.py
│
├── examples/
│   └── config.py
│
├── README.md
└── pyproject.toml
```

---

## 🧠 How It Works

TVM does **not** directly control windows via Python bindings.

Instead it:

1. Uses `xwininfo` to select a window
2. Uses `xdotool` to send input
3. Runs these in a subprocess for stability

This avoids crashes caused by native bindings.

---

## 🐞 Troubleshooting

### Nothing happens when sending commands

* Make sure the window still exists
* Try reselecting it

### TVM doesn’t launch from menu

* Run `update-desktop-database`

### Wayland issues

TVM currently requires Xorg.

---

## 📌 Categories

```text
Development Status :: 3 - Alpha
Environment :: X11 Applications
Intended Audience :: Developers
License :: OSI Approved :: MIT License
Operating System :: POSIX :: Linux
Programming Language :: Python :: 3
Topic :: Utilities
Topic :: System :: Shells
Topic :: Desktop Environment
```

---

## 📄 License

MIT License

---

## 🙌 Contributing

PRs and ideas welcome.

---

## 🔮 Roadmap

* [ ] Wayland support
* [ ] Macro recording
* [ ] Visual window selector overlay
* [ ] Plugin marketplace
* [ ] Profiles/workspaces

