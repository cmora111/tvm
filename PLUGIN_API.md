# TVM Plugin API

TVM supports user plugins loaded from:

```text
~/.config/tvm/plugins/
```

## API Version

Current plugin API version:

```python
TVM_PLUGIN_API_VERSION = 1
```

A plugin may declare the API version it expects:

```python
TVM_PLUGIN_API_VERSION = 1
```

If omitted, TVM assumes API version `1`.

Plugins with a mismatched API version are shown in the Plugin Browser as load errors and will not run.

## Optional Plugin Metadata

A plugin can provide metadata for the Plugin Browser:

```python
PLUGIN_NAME = "Hello World"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "Sends a message to the selected terminal."
TVM_PLUGIN_API_VERSION = 1
```

## Required Entry Point

Every plugin must define:

```python
def run(app, context):
    ...
```

## Context Object

`context` is a dictionary with these keys:

- `window_id` — selected target X11 window id, or `None`
- `config` — loaded TVM config module
- `plugin_dir` — path to the user plugin directory
- `args` — arguments from the config entry for the plugin button
- `app_version` — current TVM version string
- `plugin_api_version` — current supported plugin API version

## Example Plugin

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

## Example Config Entry

```python
{
    "label": "Hello World",
    "type": "plugin",
    "plugin": {
        "plugin": "hello_world",
        "args": {
            "message": "TVM is working."
        }
    }
}
```

## Stability Notes

- Plugins run inside the TVM process.
- If a plugin raises an exception, TVM shows the traceback in an error dialog.
- Plugins should avoid long blocking work on the Tkinter UI thread.
- Window interaction should go through `app.send_text_to_window(...)`.

## Compatibility Strategy

When the plugin API changes in the future:

- TVM should increment `PLUGIN_API_VERSION`
- Plugins should update `TVM_PLUGIN_API_VERSION`
- The Plugin Browser will make mismatches visible immediately
