# TVM — Terminal Virtual Macropad

TVM is a lightweight Tkinter-based macropad for Linux that sends commands to a selected terminal window.

---

## Features

- GUI-based macropad
- Click-to-select target window
- Command execution via `xdotool`
- Configurable button categories
- Plugin system with hot reload
- Visual button editor built into the app
- Macro recorder built into the app
- Desktop launcher support
- Works on Ubuntu / Xorg

---

## Requirements

- Linux (Xorg session)
- Python 3.10+
- External tools:

```bash
sudo apt install xdotool x11-utils
```

---

## Installation

Recommended with pipx:

```bash
sudo apt install pipx
pipx ensurepath
pipx install tvm
```

Run:

```bash
tvm
```

Development install:

```bash
git clone https://github.com/cmora111/tvm
cd tvm
pipx install -e .
```

Run without installing:

```bash
PYTHONPATH=src python3 -m tvm
```

---

## Configuration

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

## Command Types

TVM supports these built-in command types:

```text
select_window
spawn_terminal
send_to_window
run_detached
plugin
macro
```

The first four map to the original numeric command types automatically, so older configs continue to work.

---

## Visual Button Editor

Use the **Edit Buttons** button in the main window to open the built-in editor.

You can:
- create new buttons
- rename buttons
- move a button to a different category
- change the command type
- edit plain commands, plugin payloads, or macro JSON
- delete buttons
- create categories

Changes are saved directly to:

```text
~/.config/tvm/config.py
```

---

## Macro Recorder

Use the **Macro Recorder** button in the main window.

Workflow:
1. Click **Start**
2. Run the TVM buttons you want to capture
3. Click **Stop**
4. Click **Save as Button**
5. Choose a category and button label

TVM saves the result as a built-in `macro` command.

Example macro entry in config:

```python
Categories = {
    "Macros": {
        "My Macro": [
            "macro",
            [
                [2, "pwd"],
                [2, "ls -lah"],
                ["plugin", {"plugin": "hello", "message": "done"}],
            ],
        ]
    }
}
```

Notes:
- selecting a window is not recorded as part of a macro
- nested macros are allowed, but keep them simple to avoid loops
- recorded plugin actions preserve their plugin payload

---

## Plugin System

Plugins live in:

```text
~/.config/tvm/plugins/
```

Each plugin must define:

```python
def run(app, context):
    ...
```

### Plugin example

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

Add a button in config:

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

### Hot reload

TVM reloads plugins automatically when they change.

You can:
- edit a plugin file
- save it
- click the plugin button again

You can also click **Reload Plugins** in the main window.

---

## Desktop Integration

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

If it does not appear in the launcher right away:

```bash
update-desktop-database ~/.local/share/applications
```

---

## Project Structure

```text
tvm/
├── src/tvm/
│   ├── app.py
│   ├── cli.py
│   ├── xdo_helper.py
│   └── default_config.py
├── examples/
│   └── config.py
├── README.md
└── pyproject.toml
```

---

## How It Works

TVM uses external X11 tools for stability:

1. `xwininfo` selects a target window
2. `xdotool` sends text and keys
3. helper subprocess isolation prevents UI crashes from taking down Tkinter

---

## Troubleshooting

### Nothing happens
- reselect the target window
- make sure the terminal is still open
- make sure you are on Xorg, not Wayland

### Plugin not updating
- save the plugin file and click the button again
- or click **Reload Plugins**

### Macro saved but not visible
- reopen the category window after saving
- the main window refreshes immediately, but already-open category windows do not

---

## License

MIT License
