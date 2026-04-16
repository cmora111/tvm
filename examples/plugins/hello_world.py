"""
Example TermForge plugin.
Can live in either:
- examples/plugins/hello_world.py
- ~/.config/termforge/plugins/hello_world.py
"""

PLUGIN_NAME = "Hello World"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "Echoes a message into the selected terminal."
TermForge_PLUGIN_API_VERSION = 1


def run(app, context):
    args = context.get("args", {})
    message = args.get("message", "Hello from TermForge!")

    if context.get("window_id"):
        app.send_text_to_window(f'echo "{message}"')

    app.set_status(f"Plugin ran: {PLUGIN_NAME}")
    print(message)
