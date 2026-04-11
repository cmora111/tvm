#------------------------------------------------------------------------------#
# 0 Select a new window to send commands to                                    #
# 1 Spawn a new window                                                         #
# 2 Use window that was configured at the beginning of the tvm.py script       #
# 3 Don't need a window                                                        #
#------------------------------------------------------------------------------#

debug = {"Flag": False}

terminal = {"application": "gnome-terminal"}
# terminal = {"application": "lxterminal"}

Categories = {
    "Select Window": {
        "Select window": [0, "None"]
    },
    "Admin_CMDs": {
        "ps": [1, "ps axwwl"],
        "psa": [2, "ps axwwl | grep -i <name>"],
        "ls": [2, "ls <name>"],
        "lsg": [2, "lsg <name>"],
        "lst": [2, "lst"],
        "ns": [2, "ns"],
        "cd": [2, "cd <name>"],
        "find_grep": [2, r"find . -type f -exec grep -i <name> {} \; -print"],
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
        "Firefox": [1, "/usr/bin/firefox"],
        "Wireshark": [3, "sudo /usr/bin/wireshark &"]
    },
    "Vi": {
        "vim": [2, "vi <name>\r"],
        "PluginInstall": [2, ":PluginInstall\r"],
        "PluginList": [2, ":PluginList\r"],
        "NextColorScheme": [2, ":NextColorScheme\r"],
        "bash.initial": [2, ":-1r /home/mora/Templates/bash.initial\r"],
        "bash.tmpl": [2, ":-1r /home/mora/Templates/bash.tmpl\r"],
        "bash.comment": [2, ":-1r /home/mora/Templates/bash.comments\r"],
        "python.initial": [2, ":-1r /home/mora/Templates/python.initial\r"],
        "python.comment": [2, ":-1r /home/mora/Templates/python.comment\r"],
        "python.template": [2, ":-1r /home/mora/Templates/python.template\r"],
        "python.sub": [2, ":-1r /home/mora/Templates/python.sub\r"],
        "python.class": [2, ":-1r /home/mora/Templates/python.class\r"],
        "Write_Exit": [2, ":wq!\r"],
        "NoWrite_Exit": [2, ":q\r"],
        "Reload": [2, ":e!\r"],
        "Date_Stamp": [2, "!!date\r"]
    }
}
