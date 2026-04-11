#!/usr/bin/env python3
#------------------------------------------------------------------------------#
# tvm.py - stable pass preserving original look and button sizing              #
#------------------------------------------------------------------------------#

from __future__ import annotations

import re
import subprocess
import sys
import time
import traceback
from pathlib import Path
from tkinter import Tk, Toplevel, Label, Button, Entry, StringVar, messagebox
from typing import Optional

try:
    from xdo import Xdo
except ImportError:
    Xdo = None

BTN_DIR = str(Path("~/.btn").expanduser())
if BTN_DIR not in sys.path:
    sys.path.insert(0, BTN_DIR)

import tvm_config as cfg  # noqa: E402


class TVMApp:
    def __init__(self, master: Tk) -> None:
        self.master = master
        self.master.title("Categories")
        self.master.protocol("WM_DELETE_WINDOW", self.on_close)

        self.debug = bool(cfg.debug.get("Flag", False))
        self.application = cfg.terminal.get("application", "gnome-terminal")
        self.window_id: Optional[int] = None
        self._closed = False

        self.build_main_window()
        self.master.after(300, self.init_window_selection)

    def log(self, msg: str) -> None:
        if self.debug:
            print(msg)

    def on_close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.master.quit()
        except Exception:
            pass
        try:
            self.master.destroy()
        except Exception:
            pass

    def build_main_window(self) -> None:
        Label(
            self.master,
            text="GUI CMDs",
            bd=4,
            width=15,
            bg="lightgreen",
            fg="black",
            relief="raised",
        ).pack()

        for category in cfg.Categories:
            Button(
                self.master,
                text=category,
                width=15,
                bg="black",
                fg="yellow",
                command=lambda c=category: self.open_category_window(c),
            ).pack(pady=2)

        Button(
            self.master,
            text="Exit",
            width=15,
            bg="red",
            fg="black",
            command=self.on_close,
        ).pack(side="bottom")

    def open_category_window(self, category: str) -> None:
        win = Toplevel(self.master)
        win.title(category)
        win.protocol("WM_DELETE_WINDOW", win.destroy)

        Label(
            win,
            text=category,
            bd=4,
            width=15,
            bg="lightgreen",
            fg="black",
            relief="raised",
        ).pack()

        for subcategory in cfg.Categories[category]:
            Button(
                win,
                text=subcategory,
                width=15,
                bg="black",
                fg="yellow",
                command=lambda c=category, s=subcategory: self.select_cmd(c, s),
            ).pack(pady=2)

        Button(
            win,
            text="Exit",
            width=15,
            bg="red",
            fg="black",
            command=win.destroy,
        ).pack(side="bottom")

    def select_cmd(self, category: str, subcategory: str) -> None:
        cmd_type, cmd = cfg.Categories[category][subcategory]
        if "<name>" in cmd:
            self.prompt_window(cmd_type, cmd)
        else:
            self.run_cmd(cmd_type, cmd)

    def prompt_window(self, cmd_type: int, cmd: str) -> None:
        prompt = Toplevel(self.master)
        prompt.title("Input")
        prompt.protocol("WM_DELETE_WINDOW", prompt.destroy)

        Label(prompt, text="Enter <name> for " + cmd).pack()

        name_var = StringVar()
        entry = Entry(prompt, textvariable=name_var)
        entry.pack()
        entry.focus_set()

        def submit() -> None:
            value = name_var.get()
            new_cmd = re.sub(r"<name>", value, cmd)
            try:
                prompt.destroy()
            except Exception:
                pass
            self.run_cmd(cmd_type, new_cmd)

        Button(prompt, text="OK", width=15, command=submit).pack()
        entry.bind("<Return>", lambda _event: submit())

    def run_cmd(self, cmd_type: int, cmd: str) -> None:
        try:
            if cmd_type == 0:
                self.select_target_window()
            elif cmd_type == 1:
                self.run_cmd_spawn_terminal(cmd)
            elif cmd_type == 2:
                self.run_cmd_in_terminal(cmd)
            else:
                self.run_cmd_no_terminal(cmd)
        except Exception as exc:
            self.show_error("Command failed", f"{exc}\n\n{traceback.format_exc()}")

    def init_window_selection(self) -> None:
        try:
            self.select_target_window()
        except Exception as exc:
            self.log(f"Initial window selection failed: {exc}")

    def select_target_window(self) -> None:
        if Xdo is None:
            raise RuntimeError("python-libxdo is not installed.")

        # Hide the app during selection so it does not interfere with focus/cursor.
        try:
            self.master.withdraw()
            self.master.update_idletasks()
        except Exception:
            pass

        print("Click the window you want commands to go to")
        print()

        try:
            xdo = Xdo()
            selected = xdo.select_window_with_click()
        finally:
            try:
                self.master.deiconify()
                self.master.lift()
                self.master.focus_force()
            except Exception:
                pass

        if not selected:
            raise RuntimeError("No window selected.")

        self.window_id = selected
        self.log(f"Selected window ID: {self.window_id}")

    def run_cmd_spawn_terminal(self, cmd: str) -> None:
        self.log(f"Spawn terminal: {cmd}")
        subprocess.Popen([self.application, "--", "bash", "-lc", cmd])

    def run_cmd_no_terminal(self, cmd: str) -> None:
        self.log(f"No terminal: {cmd}")
        subprocess.Popen(cmd, shell=True)

    def run_cmd_in_terminal(self, cmd: str) -> None:
        if Xdo is None:
            raise RuntimeError("python-libxdo is not installed.")
        if not self.window_id:
            raise RuntimeError("No window selected. Use Select Window first.")

        self.log(f"Send to window {self.window_id}: {cmd}")

        xdo = Xdo()
        try:
            xdo.focus_window(self.window_id)
            time.sleep(0.08)
            xdo.enter_text_window(self.window_id, cmd.encode(), delay=1200)
            xdo.send_keysequence_window(self.window_id, b"Return", delay=1200)
        except Exception as exc:
            self.window_id = None
            raise RuntimeError(
                "Could not send text to the selected window. "
                "The target window may have been closed. Use Select window again."
            ) from exc

    @staticmethod
    def show_error(title: str, message: str) -> None:
        messagebox.showerror(title, message)


def report_callback_exception(exc_type, exc_value, exc_traceback) -> None:
    message = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    try:
        messagebox.showerror("Error", message)
    except Exception:
        print(message, file=sys.stderr)


def main() -> int:
        root = Tk()
        root.report_callback_exception = report_callback_exception
        TVMApp(root)
        root.mainloop()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
