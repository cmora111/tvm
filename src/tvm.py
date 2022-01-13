#!/usr/bin/env python3
#------------------------------------------------------------------------------#
# tvm.py, Version 1.0, Sat 09 Oct 2021 11:31:22 AM EDT, mora                   #
#------------------------------------------------------------------------------#
# NAME:          tvm.py                                                        #
#                                                                              #
# SYNOPSIS:      tvm.py [-h]                                                   #
#                                                                              #
# DESCRIPTION:   TVM (Tkinter Virtual Macropad) is gui based application to    #
#                ease the repetative long command line tasks by allowing       #
#                you to create a config file of commands.                      #
#                                                                              #
# AUTHOR:        Carlos Mora                                                   #
#                                                                              #
#------------------------------------------------------------------------------#
# HISTORY:                                                                     #
#                WHO              DATE             DESCRIPTION                 #
#------------------------------------------------------------------------------#
#                Carlos Mora      10/09/2021       First Developed             #
#------------------------------------------------------------------------------#

#------------------------------------------------------------------------------#
# imports                                                                      #
#------------------------------------------------------------------------------#

from tkinter import *
import re
import sys, os
import subprocess
from xdo import Xdo
import logging
import time

sys.path.insert(1,"~/.btn")
import tvm_config as cfg

#------------------------------------------------------------------------------#
# Debugging function setup                                                     #
#------------------------------------------------------------------------------#

import pdb
#pdb.set_trace()

#------------------------------------------------------------------------------#
# Usage function                                                               #
#------------------------------------------------------------------------------#

def usage():
    print('''

    Usage: tvm.py [-h]

    Description: tvm.py simulates a macropad. It can be configured
        to issue common commands via a click of a button.

    -h, -help,          --help                  This help

    ''')
    exit(0)

#------------------------------------------------------------------------------#
# Get command line options and setup variables and constants.                  #
#------------------------------------------------------------------------------#

runningOS = sys.platform
debug = cfg.debug["Flag"]
application = cfg.terminal["application"]
newSelectFlag = 0
windowID = 0x0

categoryButton = []
scButton = []

#------------------------------------------------------------------------------#
# Build the root window getting the info from the config file                  #
#------------------------------------------------------------------------------#

def mainWindow(master):
    master.title("Categories")
    frame = Frame(master).pack()
    label = Label(frame, text="GUI CMDs", bd=4, width=15, bg='lightgreen', fg='black', relief='raised').pack()
    button = Button(frame, text='Exit', width=15, bg='red', fg='black', command=master.destroy).pack(side='bottom')

    for category in cfg.Categories:
        btn = Button(frame, text=category, width=15, bg='black', fg='yellow')
        btn.pack(pady = 2)
        btn.bind("<Button-1>", lambda event, arg=master: NewWindow(event, arg))
        categoryButton.append(btn)

#------------------------------------------------------------------------------#
# Build subwindow from main window select using info from config window        #
#------------------------------------------------------------------------------#

def NewWindow(event, args):
    global subWindow
    w = event.widget
    try:
        newText = w.cget('text')
    except:
        print('error: ', ex)

    subWindow = Toplevel()
    subWindow.title(newText)
    slabel = Label(subWindow, text=newText, bd=4, width=15, bg='lightgreen', fg='black', relief='raised').pack()

    for subCategory in cfg.Categories[newText]:
        sc = cfg.Categories[newText][subCategory]
        data=[newText, subCategory]
        sbtn = Button(subWindow, text=subCategory, width=15, bg='black', fg='yellow')
        sbtn.pack(pady = 2)
        sbtn.bind("<Button-1>", lambda event, arg=data: selectCMD(event, arg))
        scButton.append(sbtn)

    button = Button(subWindow, text='Exit', width=15, bg='red', fg='black', command=subWindow.destroy).pack(side='bottom')

#------------------------------------------------------------------------------#
# Select a command from the subwindow                                          #
#------------------------------------------------------------------------------#

def selectCMD(event, data):
    command = cfg.Categories[data[0]][data[1]]
    (type, cmd) = command
    if "<name>" in cmd:
        promptWindow('<name>', type, cmd)
    else:
        runCMD(type, subWindow, cmd)

#------------------------------------------------------------------------------#
# If selected command requires input i.e <name> from config file               #
#------------------------------------------------------------------------------#

def promptWindow(prompt, type, cmd):
    global pbtn
    global top
    top = Toplevel(master)
    l = Label(top, text='Enter ' + prompt + " for " + cmd).pack()
    nameVar = StringVar()
    e = Entry(top, textvariable=nameVar).pack()
    pbtn = Button(top, text='OK', command=lambda cmd=cmd: cleanup(top, nameVar, type, cmd)).pack()

#------------------------------------------------------------------------------#
# After input for command replacing all occurances of <name>                   #
#------------------------------------------------------------------------------#

def cleanup(top, nameVar, type, cmd):
    global value
    value = nameVar.get()
    newCMD = re.sub('<name>', value, cmd)
    top.destroy()
    runCMD(type, subWindow, newCMD)

#------------------------------------------------------------------------------#
# The following is require if runing a command that has a ';'                  #
# as part of the command. Such as:                                             #
#    find . -type f -exec grep -i <name> {} \; -print                          #
#                                            ^                                 #
# Multipe commands can be run seperated by a ';'. But don't                    #
# want to split the 'find' command using the ';'                               #
#                                                                              #
# Thanks to Wiktor Stribiżew on stackoverflow for the solustion                #
#match = re.search(r'\bfind\s.*-exec\s.*\\;?[^;]*', cmd)                       #
#if match:                                                                     #
#    print(match.group())                                                      #
#                                                                              #
#See the regex demo. Details:                                                  #
#                                                                              #
#    \bfind - a find word that has no letter/digit/_ right before it, and then #
#    \s - a whitespace                                                         #
#    .* - zero or more chars other than line break chars, as many as possible  #
#    -exec - an -exec string                                                   #
#    \s.* - a whitespace and then zero or more chars other than line break     #
#           chars, as many as possible                                         #
#    \\ - a \ char                                                             #
#    ;? - an optional ; char                                                   #
#    [^;]* - zero or more chars other than ;                                   #
#                                                                              #
# pattern = r"\bfind\s.*-exec\s.*\\;?[^;]*"                                    #
# text = r"lsg <name>; cd <name>;find . -type f -exec grep -i <name> {} \; -print;lsg ; ps axwwl "#
# match = re.search(rx, text)                                                  #
#------------------------------------------------------------------------------#

#------------------------------------------------------------------------------#
# Run comman:                                                                  #
#     0. Used to setup the windowID upon first invokation                      #
#     1. Spawn a new terminal (application from config file)                   #
#     2. Run cmd in terminalm (windowID assigned when script is run            #
#     3. Applications that don't need a terminal to run                        #
#------------------------------------------------------------------------------#

def runCMD(type, subWindow, cmd):
    global newSelectFlag
    if type == 0:
        newSelectFlag = 1
        getWindowID(subWindow)
    elif type == 1:
    # elif type == 1 or arch == 'arm':
        runCMDSpawnTerminal(cmd)
        #os.system(cmd)
    elif type == 2:
        runCMDInTerminal(cmd)
    else:
        runCMDNoTerminal(cmd)   

def runCMDSpawnTerminal(cmd):
    if debug:
        print("1. ",cmd)
    command = application + " -- /bin/bash -c \'bash --rcfile <( cat ~/.bashrc; echo " + cmd + "; echo)\'"
    #os.system(command)
    #time.sleep(3)
    #pid = ???
    #os.system("kill -9 {0}".format(pid))
    if debug:
        print("1. ",command)

def runCMDNoTerminal(cmd):
    if debug:
        print("2. ",cmd)
    os.system(cmd)

def runCMDInTerminal(cmd):
    pdb.set_trace()
    if debug:
        print("3. " + str(windowID) + " " + cmd)
    # subprocess.call(["xdotool", "windowfocus", "--sync", windowID])
    # subprocess.call(["xdotool", "type", cmd+"\n"]) 
    xdo = Xdo()
    xdo.focus_window(windowID)
    time.sleep(1)
    print(windowID)
    return_code = "Return"
    xdo.enter_text_window(windowID, cmd.encode(), delay=1200)
    xdo.send_keysequence_window(windowID, return_code.encode(), delay=1200)

#------------------------------------------------------------------------------#
# Run application initializations.                                             #
#------------------------------------------------------------------------------#

# import platform is probably better that sys.platform
# import platform
# import os
# os.name:
#     on windows: nt
#     on ubuntu: posix
#     on mac: posix
# platform.system()
#     on windows: Windows
#     on ubuntu: Linux
#     on mac: Darwin
# platform.release()
#     on windows: 10
#     on ubuntu: 
#     on mac: 8.11.1
#
#
# From winndows:
# import sys, win32com.client
# shell = win32com.client.Dispatch("WScript.Shell")
# Now, we open a command window, change the path to C:\, and execute a dir:
#
# shell.Run("cmd /K CD C:\ & Dir")
# 
# Run a script
#WshShell.Run("powershell -file C:\\MyScript.ps1")
#
# Run one command
# WshShell.Run("powershell -command echo Test")

def init():
    if runningOS == "linux":
        pass
    elif runningOS == "win32":
        pass

    global windowID
    global newSelectFlag
    global arch
     
    # get the architecture
    arch = os.uname()[4][:3]

    # check for debug set in the tvm_config.py
    debug = cfg.debug["Flag"]    

    # Flag used to select a new window to send commands to
    newSelectFlag = 0

    # Get the initial window to send commans to
    print("Click the window you want commands to go to")
    print()

    xdo = Xdo()
    windowID = xdo.select_window_with_click()
#    winid = xdo.select_window_with_click()
    #windowID = (hex(winid))
    
#------------------------------------------------------------------------------#
# Get the windowm id of the window tosend commands to.                         #
#------------------------------------------------------------------------------#

def getWindowID(subWindow):
    global windowID
    global newSelectFlag

    subWindow.destroy()
    time.sleep(2)

    print("Click the window you want commands to go to")
    print()

    proc = subprocess.Popen(["getWindowID.py"], stdout=subprocess.PIPE, shell=True)
    (winid, err) = proc.communicate()
    #winid = os.system("getWindowID.py").read()

    windowID = winid.decode()
    if debug:
        print(windowID)

if __name__ == '__main__':
    init()

    if debug == "True":
        pdb.set_trace()

    master = Tk()
    var = IntVar()
    mainWindow(master)
    mainloop()
