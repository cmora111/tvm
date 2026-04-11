# TVM — Terminal Virtual Macropad

TVM is a lightweight Tkinter-based macropad for Linux that sends commands to a selected terminal window.

---

## 🚀 Features

* GUI-based macropad
* Click-to-select target window
* Command execution via `xdotool`
* Configurable button grid
* 🧩 Plugin system (extensible actions)
* 🔄 Plugin hot-reload (no restart required)
* 🖥️ Desktop launcher support
* Works on Ubuntu / Xorg

---

## ⚠️ Requirements

* Linux (Xorg session)
* Python 3.10+
* External tools:

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

Create it:

```bash
mkdir -p ~/.config/tvm
cp examples/config.py ~/.config/tvm/config.py
```

---

## 🧩 Plugin System

Plugins allow you to extend TVM with custom actions.

### 📁 Plugin Directory

```text
~/.config/tvm/plugins/
```

Each plugin must define:

```python
def run(app, context):
    ...
```

---

## 🔄 Plugin Hot Reload

TVM automatically reloads plugins when they change.

You can:

* Edit a plugin file
* Save it
* Click the button again → changes apply instantly

You can also manually reload plugins using the **"Reload Plugins"** button in the UI.

---

## 🧩 Plugin Example

Create a plugin:

```bash
mkdir -p ~/.config/tvm/plugins
nano ~/.config/tvm/plugins/hello.py
```

```python
def run(app, context):
    message = context.get("args", {}).get("message", "Hello from TVM!")

    window_id = context.get("window_id")

    if window_id:
        app.send_text_to_window(f'echo "{message}"')

    print(message)
```

Add a button in your config:

```python
{
    "label": "Hello",
    "type": "plugin",
    "plugin": "hello"
}
```

Example with arguments:

```python
{
    "label": "Custom Message",
    "type": "plugin",
    "plugin": "hello",
    "args": {
        "message": "This came from config!"
    }
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

TVM uses external X11 tools for stability:

1. `xwininfo` — select window
2. `xdotool` — send commands
3. subprocess isolation — prevents crashes

---

## 🐞 Troubleshooting

### Nothing happens

* Reselect the window
* Ensure terminal is focused

### Not launching from menu

```bash
update-desktop-database ~/.local/share/applications
```

### Wayland

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

PRs welcome.

---

## 🔮 Roadmap

* [ ] Wayland support
* [ ] Macro recording
* [ ] Plugin marketplace
* [ ] Profiles/workspaces
* [ ] Visual window picker

