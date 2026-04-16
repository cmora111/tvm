# TermForge example configuration
# Copy to: ~/.config/termforge/config.py

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

Window = {
    'server': None,
    'logs': None,
}

Hotkeys = {
    '<ctrl>+<alt>+d': ['Admin_CMDs', 'Deploy'],
    '<ctrl>+<alt>+l': ['Admin_CMDs', 'Logs'],
    '<ctrl>+<alt>+p': ['Admin_CMDs', 'pwd'],
}

Categories = {
    'Select Window': {
        'Select window': [0, 'None'],
    },
    'Admin_CMDs': {
        'Deploy': ['chain', [
            ['select_profile', 'server'],
            [2, 'cd <path>'],
            ['sleep', 1],
            [2, 'git pull'],
            ['sleep', 1],
            [2, 'systemctl restart myservice', {'confirm': True}],
        ]],

        'Logs': ['chain', [
            ['select_profile', 'logs'],
            [2, 'tail -15 /var/log/syslog'],
        ]],

        'ls': [2, 'ls'],
        'ps': [2, 'ps axwwl'],
        'pwd': [2, 'pwd'],
        'cd': [2, 'cd <path>'],
        'mkdir': [2, 'mkdir -p <path>'],
        'ssh': [2, 'ssh -T <user>@<host>'],
        'Danger Upgrade': [2, 'sudo apt update -y', {'confirm': True}],
    },

    'Applications': {
        'htop': [1, 'htop'],
        'Visual Studio Code': [3, 'code > /dev/null 2>&1 &'],
    },

    'Plugins': {
        'Hello World Plugin': ['plugin', 'hello_world'],
    },

    'Chain CMDs': {
        'Quick Test': ['chain', [
            [2, 'pwd'],
            [2, 'ls'],
        ]],

        'SSH Prep': ['chain', [
            [2, 'cd <path>'],
            [2, 'ssh <user>@<host>'],
        ]],

        'Danger Chain': ['chain', [
            [2, 'echo starting'],
            [2, 'sudo apt upgrade -y', {'confirm': True}],
        ]],

        'Deploy Shared': ['chain', [
            ['vars', ['path', 'user', 'host']],
            ['select_profile', 'server'],
            [2, 'cd <path>'],
            ['sleep', 1],
            [2, 'ssh -T <user>@<host>'],
            [2, 'echo Deploying from <path>'],
        ]],

        'Shared Test': ['chain', [
            ['vars', ['path']],
            [2, 'cd <path>'],
            [2, 'echo path is <path>'],
        ]],
    }

}
Favorites = [
    ["Admin_CMDs", "ls"],
    ["Admin_CMDs", "pwd"],
    ["Admin_CMDs", "ssh"],
    ["Plugins", "Hello World Plugin"],
]


Windows = {'server': 2118605}
