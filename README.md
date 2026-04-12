# TVM — Terminal Virtual Macropad

TVM is a lightweight Tkinter-based macropad for Linux that sends commands to a selected terminal window.

## Features

- GUI-based macropad
- Click-to-select target window
- Command execution via `xdotool`
- Configurable button grid
- Plugin system
- Plugin hot reload
- Plugin Browser UI
- Plugin API versioning
- Desktop launcher support
- Works on Ubuntu / Xorg

## Requirements

- Linux (Xorg session)
- Python 3.10+
- External tools:

```bash
sudo apt install xdotool x11-utils
```

## Installation

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

## Development

```bash
git clone https://github.com/cmora111/tvm
cd tvm
pipx install -e .
```

Or without installing:

```bash
PYTHONPATH=src python3 -m tvm
```

## Configuration

TVM loads config from:

```text
~/.config/tvm/config.py
```

Copy the example:

```bash
mkdir -p ~/.config/tvm
cp examples/config.py ~/.config/tvm/config.py
```

## Plugin System

Plugin files live in:

```text
~/.config/tvm/plugins/
```

Each plugin must define:

```python
def run(app, context):
    ...
```

### Plugin metadata

Plugins may also define:

```python
PLUGIN_NAME = "Hello World"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "Example plugin"
TVM_PLUGIN_API_VERSION = 1
```

### Plugin Example

Create a plugin:

```bash
mkdir -p ~/.config/tvm/plugins
nano ~/.config/tvm/plugins/hello_world.py
```

```python
PLUGIN_NAME = "Hello World"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "Example TVM plugin"
TVM_PLUGIN_API_VERSION = 1

def run(app, context):
    args = context.get("args", {})
    message = args.get("message", "Hello from TVM!")

    if context.get("window_id"):
        app.send_text_to_window(f'echo "{message}"')

    print(message)
```

Add a button in your config:

```python
{
    "label": "Hello World",
    "type": "plugin",
    "plugin": {
        "plugin": "hello_world",
        "args": {
            "message": "This came from config!"
        }
    }
}
```

## Plugin Browser

TVM includes a built-in **Plugin Browser** window.

It shows:

- plugin name
- plugin version
- plugin API version
- compatibility with the current TVM build
- file path
- last modified time
- load errors

Use it to verify that plugins loaded correctly and to spot API mismatches quickly.

## Plugin Hot Reload

TVM automatically reloads plugin files when they change.

You can also click **Reload Plugins** in the main window.

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

## Project Structure

```text
tvm/
├── src/tvm/
│   ├── app.py
│   ├── cli.py
│   ├── xdo_helper.py
│   └── default_config.py
├── examples/
│   ├── config.py
│   └── plugins/
│       └── hello_world.py
├── README.md
├── PLUGIN_API.md
└── pyproject.toml
```

## How It Works

TVM uses external X11 tools for stability:

1. `xwininfo` — select window
2. `xdotool` — send commands
3. subprocess isolation — prevents crashes in the GUI process

## Troubleshooting

### Nothing happens
- Reselect the window
- Ensure the terminal still exists

### Not launching from menu

```bash
update-desktop-database ~/.local/share/applications
```

### Wayland
TVM currently requires Xorg.

## License

MIT License
