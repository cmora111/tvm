# TVM example configuration
# Copy to: ~/.config/tvm/config.py

debug = {
    'Flag': False
}

terminal = {
    'application': 'gnome-terminal'
}

# Command entry formats:
#   [0, 'None']                         -> select target window
#   [1, 'command']                      -> open new terminal and run command
#   [2, 'command']                      -> send command to selected window
#   [3, 'command']                      -> run detached command
#   ['plugin', 'plugin_name']           -> run plugin by name
#   [2, 'dangerous command', {'confirm': True}] -> ask for confirmation first
#
# Placeholders like <name>, <user>, <host>, <path> will prompt for input.

Categories = {
    'Select Window': {
        'Select window': [0, 'None'],
    },

    'Admin_CMDs': {
        'ls': [2, 'ls'],
        'ps': [2, 'ps axwwl'],
        'pwd': [2, 'pwd'],
        'cd': [2, 'cd <path>'],
        'mkdir': [2, 'mkdir -p <path>'],
        'ssh': [2, 'ssh <user>@<host>'],
        'Danger Upgrade': [2, 'sudo apt upgrade -y', {'confirm': True}],
    },

    'Applications': {
        'htop': [1, 'htop'],
        'Visual Studio Code': [3, 'code > /dev/null 2>&1 &'],
    },

    'Plugins': {
        'Hello World Plugin': ['plugin', 'hello_world'],
    },
}
Favorites = [
    ["Admin_CMDs", "ls"],
    ["Admin_CMDs", "pwd"],
    ["Admin_CMDs", "ssh"],
    ["Plugins", "Hello World Plugin"],
]
