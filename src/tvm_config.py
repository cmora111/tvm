#------------------------------------------------------------------------------#
# 0 Select a new window to send commands to                                    #
# 1 Spawn a new window                                                         #
# 2 Use window  the was configured at the beginning of the tvm.py script       #
# 3 Don't need a window                                                        #
#                                                                              #
# Description:                                                                 #
#     Categories = {                                                           #
#         <Window label1>: = {                                                 #
#             <button label1>: [1, <command>],                                 #
#             <button label2>: [3, <command>]                                  #
#         },                                                                   #
#         <Window label2>: = {                                                 #
#             <button label1>: [2, <command>],                                 #
#             <button label2>: [1, <command>]                                  #
#         }                                                                    #
#     }                                                                        #
#                                                                              #
#   IMPORTANT:                                                                 #
#                                                                              #
#   - Example:                                                                 #
#                                                                              #
#     Categories = {                                                           #
#         'Linux CMDs': {                                                      #
#             'ls': [2, 'ls'],                                                 #
#             'ps_axwwl': [2, 'ps axwwl'],                                     #
#             'find_grep': [2, 'find . -type f -exec grep -i <name> \{\} ; -print'] #
#         },                                                                   #
#         'Applications': {                                                    #
#             'Firefox': [3, 'firefox &'],                                     #
#             'arduino': [3, 'arduino > /dev/null 2>&1 &'],                    #
#             'Glances': [1, 'glances &']                                      #
#         }                                                                    #
#     }                                                                        #
#                                                                              #
#   - 'Categories' is mandatory!!                                              #
#                                                                              #
#   - Multipe commands can be processed seperated by a ';'                     #
#                                                                              #
#   - <name> is a delimiter for being prompted before a command is processed.  #
#         Multiple '<name>'s will be prompted just once and then all           #
#         occurances of '<name>' will be replaced by the one prompt.           #
#                                                                              #
#   - Commands not containing a '<name>', will be processed immediately.       #
#                                                                              #
#   - Commands that contain a '<name>', will be prompted for '<name>' then     #
#         either a 'mkdir -p <dir>/<name>' followed by a 'cd' or a 'cd'        #
#         will be procssesed after being prompted.                             #
#                                                                              #
#   - Commands that contain a 'cd <name>' will be prompted for '<name>'        #
#         followed by a 'cd <name>'.                                           #
#                                                                              #
#   - Commands that contain a 'mkdir -p <dir>/<name>', will be prompted for    #
#        '<name>' followed by a 'cd <dir>/<name>'                              #
#         made, followed by a 'cd' to that fill directory.                     #
#                                                                              #
#   - Commands                                                                 #
#                                                                              #
#                                                                              #
#------------------------------------------------------------------------------#

debug = { "Flag": "False" }

# For other linux terminals (Ubuntu)
terminal = { "application": "gnome-terminal" }
# For raspberryy pi)
#terminal = { "application": "lxterminal" }

Categories = {
    "Select Window": {
        "Select window": [0, "None"]
    },
    "Admin_CMDs":  {
        "ps": [1, "ps axwwl"],
        "psa": [2, "ps axwwl|grep -i <name>"],
        "ls": [2, "ls <name>"],
        "cd": [2, "cd <name>"],
        "find_grep": [2, "find . -type f -exec grep -i <name> {} \; -print"],
    },
    "APT_CMDs": {
        "Update": [2, "sudo apt update"],
        "Upgrade": [2, "sudo apt upgrade -y"],
        "Install": [2, "sudo apt install <name>"],
        "Reinstall": [2, "sudo apt install -y --reinstall <name>"],
        "Purge": [2, "sudo apt purge -y <name>"],
        "Autoremove": [2, "sudo apt autoremove -y"],
        "Fix-Broken": [2, "sudo apt --fix-broken install -y"]
    },
    "Applications": {
        "Glances": [1, "glances"],
        "Firefox": [3, "firefox &"],
        "Wireshark": [3, "sudo /usr/bin/wireshark  &"]
    },
    # You can issue vi commands
    "Vi": {
        "Write_Exit": [2, ":wq!\"],
        "NoWrite_Exit": [2, ":q\"],
        "Reload": [2, ":e!\"],
        "Date_Stamp": [2, "!!date\"]
    }
}
