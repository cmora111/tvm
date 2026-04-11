📄 examples/config.py
# TVM Configuration File
# Copy this to: ~/.config/tvm/config.py

CONFIG = {
    "grid": {
        "rows": 3,
        "cols": 3
    },

    "buttons": [
        # --- Basic Commands ---
        {
            "label": "List Files",
            "type": "command",
            "command": "ls -lah"
        },
        {
            "label": "Git Status",
            "type": "command",
            "command": "git status"
        },
        {
            "label": "Clear",
            "type": "command",
            "command": "clear"
        },

        # --- Script / Multi-command ---
        {
            "label": "Update System",
            "type": "command",
            "command": "sudo apt update && sudo apt upgrade -y"
        },

        # --- Plugin Example (simple) ---
        {
            "label": "Hello Plugin",
            "type": "plugin",
            "plugin": "hello"
        },

        # --- Plugin Example with args ---
        {
            "label": "Custom Message",
            "type": "plugin",
            "plugin": "hello",
            "args": {
                "message": "Hello from TVM plugin!"
            }
        },

        # --- Empty slots (optional) ---
        {
            "label": "",
            "type": "noop"
        },
        {
            "label": "",
            "type": "noop"
        },
        {
            "label": "",
            "type": "noop"
        },
    ]
}
