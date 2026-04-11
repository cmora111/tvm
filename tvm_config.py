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
    "Passwords": {
        "github": [1, "echo \"JjM06212008\""]
    },
    "System Backup": {
        "bkp_rsync.sh": [1, "/home/mora/bin/bkp_rsync.sh -s / -d /mnt/backups"]
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
    "Cheatsheets": {
        "List": [2, "ls -C /home/mora/.cheat"],
        "Cheatsheet": [2, "cat /home/mora/.cheat/<name>"]
    },
    "LVM CMDs": {
        "lvm help": [2, "cat /home/mora/.cheat/lvm | less"],
        "pvcreate": [2, "sudo pvcreate <name>"],
        "pvscan": [2, "sudo pvscan"],
        "pvs": [2, "sudo pvs"],
        "pvremove": [2, "sudo pvremove <name>"],
        "vgcreate": [2, "sudo vgcreate <name>"],
        "vgs": [2, "sudo vgs"],
        "vgremove": [2, "sudo vgremove <name>"],
        "lvcreate": [2, "sudo lvcreate <name>"],
        "lvs": [2, "sudo lvs"],
        "lvremove": [2, "sudo lvremove <name>"]
    },
    "Projects_CMDS": {
        "New": [2, "pgc <name>; pgt <name>"],
        "ChgDir": [2, "pgt <name>"],
        "edit_README": [2, "pgt <name>; retext README.md"],
        "Tests_Dir": [2, "pgt <name>; cd tests"]
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
        "dbeaver": [3, "/usr/bin/dbeaver > /dev/null 2>&1 &"],
        "Glances": [1, "glances"],
        "Zoom": [3, "zoom"],
        "Cura": [3, "/home/mora/bin/cura > /dev/null 2>&1 &"],
        "prusa-slicer": [3, "/usr/bin/prusa-slicer > /dev/null 2>&1 &"],
        "prusa-gcodeviewer": [3, "/usr/bin/prusa-gcodeviewer > /dev/null 2>&1 &"],
        "Blender": [3, "/usr/bin/blender > /dev/null 2>&1 &"],
        "Arduino": [3, "/home/mora/Projects/Arduino/arduino > /dev/null 2>&1 &"],
        "Mu": [3, "/usr/bin/mu-editor > /dev/null 2>&1 &"],
        "Visual": [3, "/usr/bin/code > /dev/null 2>&1 &"],
        "Asciiquarium": [1, "/home/mora/bin/asciiquarium"],
        "Openaudible": [3, "/home/mora/Projects/Openaudible/openaudible > /dev/null 2>&1 &"],
        "xLights": [3, "/home/mora/Projects/xLights/xLights > /dev/null 2>&1 &"],
        "trilium": [3, "trilium > /dev/null 2>&1 &"],
        "Wireshark": [3, "sudo /usr/bin/wireshark &"]
    },
    "Print_3D_CMDs": {
        "Mount sdh1": [2, "sudo mount /dev/sdh1 /mnt"],
        "uMount sdh1": [2, "sudo umount /dev/sdh1"],
        "cd_3D_Print": [2, "cd /home/mora/3D_Print/<name>"],
        "mdir_3D_Print": [2, "mkdir -p /home/mora/3D_Print/<name> && cd /home/mora/3D_Print/<name> && mkdir -p gcode"],
        "mkdir SD": [2, "mkdir -p /media/mora/79C0-64B7/<name>; cd /media/mora/79C0-64B7/<name>"],
        "cp SD": [2, "cp * /media/mora/79C0-64B7/<name>"],
        "mkdir_cp2SD": [2, "cd /home/mora/3D_Print/<name>; cp /home/mora/3D_Print/<name>/gcode/* /media/mora/79C0-64B7/<name>"]
    },
    "Git_CMDs": {
        "Git Init": [2, "git init"],
        "Git Add": [2, "git add <name>"],
        "Git Commit": [2, "git commit"],
        "Git Push": [2, "git push -u origin main"],
        "Git Clone": [2, "git clone "]
    },
    "Ssh": {
        "R400": [2, "ssh pi@r400"],
        "Alienware": [2, "ssh -T mora@alienware"],
    },
    "DB": {
        "Grocery": [2, "mysql -u root -p"]
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
