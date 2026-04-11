
from __future__ import annotations

import os
import re
import shlex
import subprocess
import time
import traceback
from pathlib import Path
from tkinter import (
    Tk,
    Toplevel,
    Frame,
    Label,
    Button,
    Entry,
    StringVar,
    messagebox,
)

try:
    from xdo import Xdo
except Exception:
    Xdo = None

APP_NAME = "TVM"
CONFIG_DIR = Path.home() / ".config" / "tvm"
CONFIG_FILE = CONFIG_DIR / "config.py"


def load_config():
    if CONFIG_FILE.exists():
        import importlib.util

        spec = importlib.util.spec_from_file_location("tvm_user_config", CONFIG_FILE)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

    from . import default_config
    return default_config


class TVMApp:
    def __init__(self, root: Tk, cfg) -> None:
        self.root = root
        self.cfg = cfg
        self.root.title("Categories")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.debug = bool(getattr(cfg, "debug", {}).get("Flag", False))
        self.application = getattr(cfg, "terminal", {}).get("application", "gnome-terminal")
        self.window_id = None

        self.build_main()
        self.root.after(250, self.safe_initial_select)

    def log(self, msg: str) -> None:
        if self.debug:
            print(msg)

    def on_close(self) -> None:
        try:
            self.root.quit()
        finally:
            self.root.destroy()

    def build_main(self) -> None:
        frame = Frame(self.root)
        frame.pack()

        Label(
            frame,
            text="GUI CMDs",
            bd=4,
            width=15,
            bg="lightgreen",
            fg="black",
            relief="raised",
        ).pack()

        for category in self.cfg.Categories:
            Button(
                frame,
                text=category,
                width=15,
                bg="black",
                fg="yellow",
                command=lambda c=category: self.open_category(c),
            ).pack(pady=2)

        Button(
            frame,
            text="Exit",
            width=15,
            bg="red",
            fg="black",
            command=self.on_close,
        ).pack(side="bottom")

    def open_category(self, category: str) -> None:
        win = Toplevel(self.root)
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

        for subcategory in self.cfg.Categories[category]:
            Button(
                win,
                text=subcategory,
                width=15,
                bg="black",
                fg="yellow",
                command=lambda c=category, s=subcategory, w=win: self.select_cmd(w, c, s),
            ).pack(pady=2)

        Button(
            win,
            text="Exit",
            width=15,
            bg="red",
            fg="black",
            command=win.destroy,
        ).pack(side="bottom")

    def select_cmd(self, parent_window, category: str, subcategory: str) -> None:
        cmd_type, cmd = self.cfg.Categories[category][subcategory]
        if "<name>" in cmd:
            self.prompt_window(cmd_type, cmd)
        else:
            self.run_cmd(cmd_type, cmd, parent_window)

    def prompt_window(self, cmd_type: int, cmd: str) -> None:
        prompt = Toplevel(self.root)
        prompt.title("Input")
        prompt.protocol("WM_DELETE_WINDOW", prompt.destroy)

        Label(prompt, text=f"Enter <name> for {cmd}").pack()

        name_var = StringVar()
        entry = Entry(prompt, textvariable=name_var)
        entry.pack()
        entry.focus_set()

        def submit() -> None:
            value = name_var.get().strip()
            new_cmd = re.sub(r"<name>", value, cmd)
            prompt.destroy()
            self.run_cmd(cmd_type, new_cmd, None)

        Button(prompt, text="OK", command=submit).pack()
        entry.bind("<Return>", lambda _event: submit())

    def safe_initial_select(self) -> None:
        try:
            self.select_target_window()
        except Exception as exc:
            self.log(f"Initial selection skipped: {exc}")

    def select_target_window(self) -> None:
        if Xdo is None:
            raise RuntimeError(
                "Missing xdo binding. Install your preferred binding first, for example "
                "`pip install xdo` or `pip install python-libxdo-ng`, plus the system libxdo package."
            )

        self.root.withdraw()
        try:
            selected = Xdo().select_window_with_click()
        finally:
            self.root.deiconify()
            self.root.lift()

        if not selected:
            raise RuntimeError("No window selected.")
        self.window_id = selected
        self.log(f"Selected window: {self.window_id}")

    def run_cmd(self, cmd_type: int, cmd: str, current_window=None) -> None:
        try:
            if current_window is not None and current_window.winfo_exists():
                current_window.destroy()

            if cmd_type == 0:
                self.select_target_window()
            elif cmd_type == 1:
                self.spawn_terminal(cmd)
            elif cmd_type == 2:
                self.send_to_selected_window(cmd)
            elif cmd_type == 3:
                self.run_detached(cmd)
            else:
                raise RuntimeError(f"Unknown command type: {cmd_type}")
        except Exception as exc:
            self.show_error("Command failed", f"{exc}\n\n{traceback.format_exc()}")

    def spawn_terminal(self, cmd: str) -> None:
        subprocess.Popen([self.application, "--", "bash", "-lc", cmd])

    def run_detached(self, cmd: str) -> None:
        subprocess.Popen(cmd, shell=True)

    def send_to_selected_window(self, cmd: str) -> None:
        if Xdo is None:
            raise RuntimeError("xdo binding is not installed.")
        if not self.window_id:
            raise RuntimeError("No target window selected.")

        xdo = Xdo()
        try:
            xdo.focus_window(self.window_id)
            time.sleep(0.1)
            xdo.enter_text_window(self.window_id, cmd.encode(), delay=1200)
            xdo.send_keysequence_window(self.window_id, b"Return", delay=1200)
        except Exception as exc:
            raise RuntimeError(
                "Could not send command to the selected window. "
                "The target may have closed. Re-select the window."
            ) from exc

    @staticmethod
    def show_error(title: str, message: str) -> None:
        messagebox.showerror(title, message)


def ensure_user_config() -> None:
    if CONFIG_FILE.exists():
        return
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    from . import default_config
    CONFIG_FILE.write_text(
        "debug = " + repr(default_config.debug) + "\n\n"
        "terminal = " + repr(default_config.terminal) + "\n\n"
        "Categories = " + repr(default_config.Categories) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    ensure_user_config()
    cfg = load_config()
    root = Tk()
    app = TVMApp(root, cfg)
    root.mainloop()
    return 0
