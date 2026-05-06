from __future__ import annotations

import importlib.util
import json
import logging
import pprint
import re
import subprocess
import sys
import time
import copy
import traceback
import shutil
from datetime import datetime

try:
    from pynput import keyboard as pynput_keyboard
except Exception:
    pynput_keyboard = None
from pathlib import Path
from tkinter import (
    BOTH,
    END,
    LEFT,
    RIGHT,
    X,
    Y,
    Button,
    Entry,
    Frame,
    Label,
    Listbox,
    Menu,
    OptionMenu,
    Scrollbar,
    StringVar,
    filedialog,
    Text,
    Tk,
    Toplevel,
    messagebox,
    filedialog,
)

APP_NAME = "TermForge"
APP_VERSION = "0.3.4"
PLUGIN_API_VERSION = 1
MAX_HISTORY = 30

CONFIG_DIR = Path.home() / ".config" / "termforge"
CONFIG_FILE = CONFIG_DIR / "config.py"
PLUGIN_DIR = CONFIG_DIR / "plugins"
STATE_FILE = CONFIG_DIR / "state.json"
LOG_FILE = CONFIG_DIR / "termforge.log"
HELPER_TIMEOUT_SECONDS = 20
PLACEHOLDER_RE = re.compile(r"<([^<>]+)>")

CONFIG_DIR.mkdir(parents=True, exist_ok=True)
PLUGIN_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


class TermForgeError(RuntimeError):
    pass


def load_config():
    if CONFIG_FILE.exists():
        spec = importlib.util.spec_from_file_location("termforge_user_config", CONFIG_FILE)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    from . import default_config
    return default_config


def ensure_user_config() -> None:
    if CONFIG_FILE.exists():
        return
    from . import default_config
    lines = [
        "# TermForge user configuration",
        "# Edit Categories below.",
        "",
        f"terminal = {repr(getattr(default_config, 'terminal', {'application': 'gnome-terminal'}))}",
        f"debug = {repr(getattr(default_config, 'debug', {'Flag': False}))}",
        "Windows = {}",
        f"Favorites = {repr(getattr(default_config, 'Favorites', [])) if hasattr(default_config, 'Favorites') else '[]'}",
        "Recent = []",
        "Usage = {}",
        "Hotkeys = {}",
        "DisabledPlugins = []",
        f"Categories = {repr(getattr(default_config, 'Categories', {}))}",
        "ChainTemplates = {}",
        "",
    ]
    CONFIG_FILE.write_text("\n".join(lines), encoding="utf-8")


def parse_command_entry(entry):
    if isinstance(entry, (list, tuple)):
        if len(entry) == 2:
            return entry[0], entry[1], {}
        if len(entry) >= 3:
            options = entry[2] if isinstance(entry[2], dict) else {}
            return entry[0], entry[1], options
    raise ValueError(f"Invalid command entry format: {entry!r}")


class MultiFieldPrompt:
    def __init__(
        self,
        parent,
        title: str,
        fields: list[str],
        defaults: dict[str, str] | None = None,
        heading: str = "Enter values",
    ):
        self.parent = parent
        self.fields = fields
        self.defaults = defaults or {}
        self.result: dict[str, str] | None = None

        self.window = Toplevel(parent)
        self.window.title(title)
        self.window.transient(parent)
        self.window.grab_set()
        self.window.resizable(False, False)
        self.window.protocol("WM_DELETE_WINDOW", self.cancel)

        container = Frame(self.window, padx=10, pady=10)
        container.pack(fill=BOTH, expand=True)

        Label(
            container,
            text=heading,
            bd=2,
            relief="groove",
            width=30,
            bg="lightgreen",
            fg="black",
        ).pack(pady=(0, 10))

        self.entries: dict[str, Entry] = {}
        for field in fields:
            row = Frame(container)
            row.pack(fill=X, pady=3)
            Label(row, text=f"{field}:", width=12, anchor="w").pack(side=LEFT)
            entry = Entry(row, width=40)
            entry.pack(side=RIGHT, fill=X, expand=True)
            entry.insert(0, self.defaults.get(field, ""))
            self.entries[field] = entry

        buttons = Frame(container)
        buttons.pack(fill=X, pady=(12, 0))
        Button(buttons, text="OK", width=12, bg="darkgreen", fg="white", command=self.submit).pack(side=LEFT)
        Button(buttons, text="Cancel", width=12, bg="red", fg="black", command=self.cancel).pack(side=RIGHT)

        if fields:
            self.entries[fields[0]].focus_set()

        self.window.bind("<Return>", lambda _e: self.submit())
        self.window.bind("<Escape>", lambda _e: self.cancel())

    def submit(self):
        self.result = {name: entry.get() for name, entry in self.entries.items()}
        self.window.destroy()

    def cancel(self):
        self.result = None
        self.window.destroy()

    def show(self) -> dict[str, str] | None:
        self.parent.wait_window(self.window)
        return self.result


class ChainRunnerWindow:
    def __init__(self, parent, total_steps: int):
        self.window = Toplevel(parent)
        self.window.title("Chain Runner")
        self.window.geometry("820x500")
        self.window.transient(parent)

        outer = Frame(self.window, padx=8, pady=8)
        outer.pack(fill=BOTH, expand=True)

        Label(
            outer,
            text=f"Chain Runner — {total_steps} step(s)",
            bd=4,
            width=40,
            bg="lightgreen",
            fg="black",
            relief="raised",
        ).pack(pady=(0, 8))

        self.output = Text(outer, wrap="word", height=18, width=90)
        self.output.pack(fill=BOTH, expand=True)
        self.output.insert("end", "Chain started.\n")
        self.output.see("end")

        button_row = Frame(outer)
        button_row.pack(fill=X, pady=(8, 0))

        Button(
            button_row,
            text="Copy Log",
            width=14,
            bg="#2f5597",
            fg="white",
            command=self.copy_log,
        ).pack(side=LEFT, padx=(0, 6))

        Button(
            button_row,
            text="Save Log",
            width=14,
            bg="#3d6d3d",
            fg="white",
            command=self.save_log,
        ).pack(side=LEFT, padx=(0, 6))

        Button(
            button_row,
            text="Clear Log",
            width=14,
            bg="#7f6000",
            fg="white",
            command=self.clear_log,
        ).pack(side=LEFT, padx=(0, 6))

        Button(
            button_row,
            text="Close",
            width=14,
            bg="red",
            fg="black",
            command=self.window.destroy,
        ).pack(side=RIGHT)

    def log(self, marker: str, message: str) -> None:
        self.output.insert("end", f"{marker} {message}\n")
        self.output.see("end")
        self.output.update_idletasks()

    def get_log_text(self) -> str:
        return self.output.get("1.0", END).strip()


    def copy_log(self) -> None:
        text = self.get_log_text()
        if not text:
            messagebox.showinfo("Copy Log", "Log is empty.")
            return

        self.window.clipboard_clear()
        self.window.clipboard_append(text)
        self.window.update()
        messagebox.showinfo("Copy Log", "Chain log copied to clipboard.")


    def save_log(self) -> None:
        text = self.get_log_text()
        if not text:
            messagebox.showinfo("Save Log", "Log is empty.")
            return

        target = filedialog.asksaveasfilename(
            title="Save Chain Execution Log",
            defaultextension=".log",
            initialfile="termforge_chain.log",
            filetypes=[
                ("Log files", "*.log"),
                ("Text files", "*.txt"),
                ("All files", "*.*"),
            ],
        )

        if not target:
            return

        Path(target).write_text(text + "\n", encoding="utf-8")
        messagebox.showinfo("Save Log", f"Saved chain log to:\n\n{target}")


    def clear_log(self) -> None:
        self.output.delete("1.0", END)

    def step_running(self, index: int, total: int, message: str) -> None:
        self.log("[>]", f"[{index}/{total}] {message}")

    def step_done(self, message: str) -> None:
        self.log("[✓]", message)

    def step_failed(self, message: str) -> None:
        self.log("[x]", message)

    def finished(self) -> None:
        self.log("[✓]", "Chain complete.")



class HotkeyEditorWindow:
    def __init__(self, app):
        self.app = app
        self.window = Toplevel(app.root)
        self.window.title("Hotkey Editor")
        self.window.geometry("900x520")
        self.window.transient(app.root)

        outer = Frame(self.window, padx=8, pady=8)
        outer.pack(fill=BOTH, expand=True)

        Label(
            outer,
            text="Hotkey Editor",
            bd=4,
            width=32,
            bg="lightgreen",
            fg="black",
            relief="raised",
        ).pack(pady=(0, 8))

        top = Frame(outer)
        top.pack(fill=BOTH, expand=True)

        left = Frame(top)
        left.pack(side=LEFT, fill=Y)

        right = Frame(top)
        right.pack(side=RIGHT, fill=BOTH, expand=True, padx=(10, 0))

        self.listbox = Listbox(left, width=40, height=18)
        self.listbox.pack(side=LEFT, fill=Y)
        scrollbar = Scrollbar(left, command=self.listbox.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.listbox.config(yscrollcommand=scrollbar.set)

        form = Frame(right)
        form.pack(fill=X)

        Label(form, text="Hotkey:", width=14, anchor="w").grid(row=0, column=0, sticky="w", pady=3)
        self.hotkey_var = StringVar()
        Entry(form, textvariable=self.hotkey_var, width=42).grid(row=0, column=1, sticky="ew", pady=3)

        Label(form, text="Category:", width=14, anchor="w").grid(row=1, column=0, sticky="w", pady=3)
        self.category_var = StringVar()
        self.category_entry = Entry(form, textvariable=self.category_var, width=42)
        self.category_entry.grid(row=1, column=1, sticky="ew", pady=3)

        Label(form, text="Command:", width=14, anchor="w").grid(row=2, column=0, sticky="w", pady=3)
        self.command_var = StringVar()
        self.command_entry = Entry(form, textvariable=self.command_var, width=42)
        self.command_entry.grid(row=2, column=1, sticky="ew", pady=3)

        form.grid_columnconfigure(1, weight=1)

        help_text = Text(right, wrap="word", height=14, width=60)
        help_text.pack(fill=BOTH, expand=True, pady=(10, 0))
        help_text.insert(
            "1.0",
            "Examples:\n"
            "  <ctrl>+<alt>+d\n"
            "  <ctrl>+<shift>+p\n"
            "  <ctrl>+<alt>+l\n\n"
            "Target format:\n"
            "  Category = a top-level key in Categories\n"
            "  Command = a command name inside that category\n\n"
            "Tip: use the Search UI in the main window to verify category/command names.\n",
        )
        help_text.config(state="disabled")

        button_row = Frame(outer)
        button_row.pack(fill=X, pady=(10, 0))

        Button(button_row, text="Load Selected", width=16, bg="#2f5597", fg="white", command=self.load_selected).pack(side=LEFT, padx=(0, 6))
        Button(button_row, text="Save Mapping", width=16, bg="darkgreen", fg="white", command=self.save_mapping).pack(side=LEFT, padx=(0, 6))
        Button(button_row, text="Delete Mapping", width=16, bg="#7f6000", fg="white", command=self.delete_mapping).pack(side=LEFT, padx=(0, 6))
        Button(button_row, text="Reload Hotkeys", width=16, bg="navy", fg="white", command=self.reload_hotkeys).pack(side=LEFT, padx=(0, 6))
        Button(button_row, text="Close", width=16, bg="red", fg="black", command=self.window.destroy).pack(side=RIGHT)

        self.snapshot = []
        self.listbox.bind("<<ListboxSelect>>", self.on_select)
        self.refresh()

    def refresh(self):
        self.snapshot.clear()
        self.listbox.delete(0, END)
        hotkeys = self.app.get_hotkeys_dict()
        for hotkey, target in sorted(hotkeys.items()):
            try:
                category, command = self.app._normalize_hotkey_target(target)
            except Exception:
                category, command = "<invalid>", repr(target)
            self.snapshot.append((hotkey, category, command))
            self.listbox.insert(END, f"{hotkey} -> {category} / {command}")

    def on_select(self, _event=None):
        idxs = self.listbox.curselection()
        if not idxs:
            return
        hotkey, category, command = self.snapshot[idxs[0]]
        self.hotkey_var.set(hotkey)
        self.category_var.set(category)
        self.command_var.set(command)

    def load_selected(self):
        self.on_select()

    def save_mapping(self):
        hotkey = self.hotkey_var.get().strip()
        category = self.category_var.get().strip()
        command = self.command_var.get().strip()

        if not hotkey or not category or not command:
            messagebox.showerror("Hotkey Editor", "Hotkey, category, and command are all required.")
            return

        categories = getattr(self.app.cfg, "Categories", {})
        if category not in categories:
            messagebox.showerror("Hotkey Editor", f"Unknown category: {category}")
            return
        if command not in categories[category]:
            messagebox.showerror("Hotkey Editor", f"Unknown command in {category}: {command}")
            return

        hotkeys = self.app.get_hotkeys_dict()
        hotkeys[hotkey] = [category, command]
        self.app.persist_hotkeys()
        self.app.initialize_hotkeys()
        self.app.set_status(f"Saved hotkey {hotkey} -> {category}/{command}")
        self.refresh()

    def delete_mapping(self):
        hotkey = self.hotkey_var.get().strip()
        if not hotkey:
            messagebox.showerror("Hotkey Editor", "Enter or select a hotkey to delete.")
            return

        hotkeys = self.app.get_hotkeys_dict()
        if hotkey not in hotkeys:
            messagebox.showerror("Hotkey Editor", f"Hotkey not found: {hotkey}")
            return

        del hotkeys[hotkey]
        self.app.persist_hotkeys()
        self.app.initialize_hotkeys()
        self.app.set_status(f"Deleted hotkey {hotkey}")
        self.hotkey_var.set("")
        self.category_var.set("")
        self.command_var.set("")
        self.refresh()

    def reload_hotkeys(self):
        self.app.initialize_hotkeys()
        self.app.set_status("Hotkeys reloaded from config.")
        self.refresh()


class PluginManagerWindow:
    def __init__(self, app):
        self.app = app
        self.window = Toplevel(app.root)
        self.window.title("Plugin Manager")
        self.window.geometry("920x540")
        self.window.transient(app.root)

        outer = Frame(self.window, padx=8, pady=8)
        outer.pack(fill=BOTH, expand=True)

        Label(
            outer,
            text="Plugin Manager",
            bd=4,
            width=34,
            bg="lightgreen",
            fg="black",
            relief="raised",
        ).pack(pady=(0, 8))

        body = Frame(outer)
        body.pack(fill=BOTH, expand=True)

        left = Frame(body)
        left.pack(side=LEFT, fill=Y)

        right = Frame(body)
        right.pack(side=RIGHT, fill=BOTH, expand=True, padx=(10, 0))

        self.listbox = Listbox(left, width=42, height=20)
        self.listbox.pack(side=LEFT, fill=Y)
        scrollbar = Scrollbar(left, command=self.listbox.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.listbox.config(yscrollcommand=scrollbar.set)

        self.info = Text(right, wrap="word", height=20, width=70)
        self.info.pack(fill=BOTH, expand=True)

        button_row = Frame(outer)
        button_row.pack(fill=X, pady=(10, 0))

        Button(button_row, text="Run", width=14, bg="darkgreen", fg="white", command=self.run_selected).pack(side=LEFT, padx=(0, 6))
        Button(button_row, text="Enable", width=14, bg="#2f5597", fg="white", command=self.enable_selected).pack(side=LEFT, padx=(0, 6))
        Button(button_row, text="Disable", width=14, bg="#7f6000", fg="white", command=self.disable_selected).pack(side=LEFT, padx=(0, 6))
        Button(button_row, text="Reload", width=14, bg="navy", fg="white", command=self.reload_plugins).pack(side=LEFT, padx=(0, 6))
        Button(button_row, text="Open Folder", width=14, bg="#444444", fg="white", command=self.app.open_plugin_folder).pack(side=LEFT, padx=(0, 6))
        Button(button_row, text="Close", width=14, bg="red", fg="black", command=self.window.destroy).pack(side=RIGHT)

        self.snapshot = []
        self.listbox.bind("<<ListboxSelect>>", self.show_info)
        self.refresh()

    def collect_snapshot(self):
        rows = []
        disabled = set(self.app.get_disabled_plugins())
        discovered = sorted({p.stem for p in PLUGIN_DIR.glob("*.py")})
        for name in discovered:
            if name in disabled:
                rows.append({
                    "status": "disabled",
                    "name": name,
                    "display_name": name,
                    "version": "-",
                    "description": "Disabled by user.",
                    "error": "",
                })
                continue
            if name in self.app.plugins:
                plugin = self.app.plugins[name]
                meta = getattr(plugin, "__termforge_metadata__", {})
                rows.append({
                    "status": "loaded",
                    "name": name,
                    "display_name": meta.get("display_name", name),
                    "version": meta.get("plugin_version", "unknown"),
                    "description": meta.get("description", "(no description)"),
                    "error": "",
                })
            else:
                rows.append({
                    "status": "error",
                    "name": name,
                    "display_name": name,
                    "version": "-",
                    "description": "",
                    "error": self.app.plugin_errors.get(name, "Unknown plugin load error."),
                })
        return rows

    def refresh(self):
        self.app.load_plugins(force=False)
        self.snapshot = self.collect_snapshot()
        self.listbox.delete(0, END)
        for item in self.snapshot:
            prefix = {"loaded": "[OK]", "disabled": "[OFF]", "error": "[ERR]"}.get(item["status"], "[?]")
            self.listbox.insert(END, f"{prefix} {item['display_name']} ({item['name']})")
        self.info.delete("1.0", END)
        self.info.insert("1.0", "Select a plugin to inspect.\n")

    def current_item(self):
        idxs = self.listbox.curselection()
        if not idxs:
            return None
        return self.snapshot[idxs[0]]

    def show_info(self, _event=None):
        item = self.current_item()
        if not item:
            return
        lines = [
            f"Name: {item['display_name']}",
            f"Internal name: {item['name']}",
            f"Status: {item['status']}",
            f"Version: {item['version']}",
            "",
        ]
        if item["description"]:
            lines.extend(["Description:", item["description"], ""])
        if item["error"]:
            lines.extend(["Error:", item["error"], ""])
        self.info.delete("1.0", END)
        self.info.insert("1.0", "\n".join(lines))

    def run_selected(self):
        item = self.selected_item()

        if not item:
            return

        self.window.destroy()
        self.app.set_status(f'Palette run: {item["category"]}/{item["name"]}')
        self.app.select_cmd(None, item["category"], item["name"])

    def disable_selected(self):
        item = self.current_item()
        if not item:
            return
        self.app.disable_plugin(item["name"])
        self.app.set_status(f"Disabled plugin: {item['name']}")
        self.refresh()

    def enable_selected(self):
        item = self.current_item()
        if not item:
            return
        self.app.enable_plugin(item["name"])
        self.app.set_status(f"Enabled plugin: {item['name']}")
        self.refresh()

    def reload_plugins(self):
        self.app.load_plugins(force=True)
        self.app.set_status("Plugins reloaded.")
        self.refresh()




class ChainBuilderWindow:
    STEP_KINDS = ["vars", "select_profile", "sleep", "send", "spawn", "detached"]

    def __init__(self, parent, app, initial_steps=None):
        self.parent = parent
        self.app = app
        self.result = None
        self.window = Toplevel(parent)
        self.window.title("Visual Chain Builder")
        self.window.geometry("1100x700")
        self.window.transient(parent)
        self.window.grab_set()
        self.build_menu()

        self.steps = list(initial_steps or [])

        outer = Frame(self.window, padx=8, pady=8)
        outer.pack(fill=BOTH, expand=True)

        Label(
            outer,
            text="Visual Chain Builder",
            bd=4,
            width=32,
            bg="lightgreen",
            fg="black",
            relief="raised",
        ).pack(pady=(0, 8))

        top_actions = Frame(outer)
        top_actions.pack(fill=X, pady=(0, 8))

        Button(
            top_actions,
            text="Apply to Editor",
            width=18,
            bg="navy",
            fg="white",
            command=self.apply_to_editor_now,
        ).pack(side=LEFT, padx=(0, 6))

        Button(
            top_actions,
            text="Templates",
            width=14,
            bg="#555577",
            fg="white",
            command=self.manage_chain_templates,
        ).pack(side=LEFT, padx=(0, 6))

        Button(
            top_actions,
            text="Close",
            width=12,
            bg="red",
            fg="black",
            command=self.close,
        ).pack(side=RIGHT)

        top = Frame(outer)
        top.pack(fill=BOTH, expand=True)

        left = Frame(top)
        left.pack(side=LEFT, fill=Y)

        right = Frame(top)
        right.pack(side=RIGHT, fill=BOTH, expand=True, padx=(10, 0))

        self.listbox = Listbox(left, width=42, height=22)
        self.listbox.pack(side=LEFT, fill=Y)
        scrollbar = Scrollbar(left, command=self.listbox.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.listbox.config(yscrollcommand=scrollbar.set)

        form = Frame(right)
        form.pack(fill=X)

        Label(form, text="Step Kind:", width=14, anchor="w").grid(row=0, column=0, sticky="w", pady=3)
        self.kind_var = StringVar(value="send")
        kind_menu = OptionMenu(form, self.kind_var, *self.STEP_KINDS)
        kind_menu.config(width=38)
        kind_menu.grid(row=0, column=1, sticky="w", pady=3)

        self.value_label = Label(form, text="Value:", width=14, anchor="nw")
        self.value_label.grid(row=1, column=0, sticky="nw", pady=3)
        self.value_text = Text(form, height=7, width=70, wrap="word")
        self.value_text.grid(row=1, column=1, sticky="nsew", pady=3)

        self.hint_var = StringVar(value="")
        Label(form, textvariable=self.hint_var, anchor="w", fg="#333333").grid(row=2, column=1, sticky="w", pady=(0, 6))

        help_box = Text(right, height=14, wrap="word")
        help_box.pack(fill=BOTH, expand=True, pady=(10, 0))
        help_box.insert(
            "1.0",
            "Kinds:\n"
            "  vars            value = JSON list, e.g. [\"path\", \"host\"]\n"
            "  select_profile  value = profile name, e.g. server\n"
            "  sleep           value = seconds, e.g. 1\n"
            "  send            value = terminal command, becomes [2, \"...\"]\n"
            "  spawn           value = new terminal command, becomes [1, \"...\"]\n"
            "  detached        value = detached command, becomes [3, \"...\"]\n\n"
            "Examples:\n"
            "  kind=vars\n"
            "  value=[\"path\", \"host\"]\n\n"
            "  kind=send\n"
            "  value=cd <path>\n"
            "  Ctrl+I       = Insert Before\n"
            "  Ctrl+R       = Run Selected Step\n"
            "  Ctrl+Shift+R = Run To End\n"
            "  Ctrl+Shift+D = Dry Run Preview\n"
            "  Ctrl+Alt+d   = Dry Run Preview with Value\n"
            "  <home>       = Move to Top\n"
            "  <end>        = Move to Bottom\n"
        )
        help_box.config(state="disabled")

        btns = Frame(outer)
        btns.pack(fill=X, pady=(10, 0))
        Button(btns, text="Add / Update Step", width=16, bg="darkgreen", fg="white", command=self.add_or_update_step).pack(side=LEFT, padx=(0, 6))
        Button(
            btns,
            text="Insert Before",
            width=14,
            bg="#2f5597",
            fg="white",
            command=self.insert_step_before,
        ).pack(side=LEFT, padx=(0, 6))
        Button(
            btns,
            text="Validate Chain",
            width=14,
            bg="#555577",
            fg="white",
            command=self.validate_chain_with_notice,
        ).pack(side=LEFT, padx=(0, 6))
        Button(
            btns,
            text="Run Selected Step",
            width=16,
            bg="#2f5597",
            fg="white",
            command=self.run_selected_step,
        ).pack(side=LEFT, padx=(0, 6))
        Button(
            btns,
            text="Dry Run",
            width=12,
            bg="#555577",
            fg="white",
            command=self.show_dry_run_preview,
        ).pack(side=LEFT, padx=(0, 6))
        Button(
            btns,
            text="Dry Run + Vars",
            width=14,
            bg="#555577",
            fg="white",
            command=self.show_dry_run_preview_with_values,
        ).pack(side=LEFT, padx=(0, 6))
        Button(btns, text="Load Selected", width=14, bg="#2f5597", fg="white", command=self.load_selected).pack(side=LEFT, padx=(0, 6))

        self.drag_index = None

        self.listbox.bind("<Button-1>", self.on_drag_start)
        self.listbox.bind("<B1-Motion>", self.on_drag_motion)
        self.window.bind("<Control-i>", lambda _e: self.insert_step_before())
        self.window.bind("<Control-r>", self.run_selected_step_shortcut)
        self.window.bind("<Control-R>", self.run_selected_step_shortcut)
        self.listbox.bind("<Control-r>", self.run_selected_step_shortcut)
        self.listbox.bind("<Control-R>", self.run_selected_step_shortcut)
        self.window.bind("<Control-Shift-R>", self.run_from_selected_to_end_shortcut)
        self.listbox.bind("<Control-Shift-R>", self.run_from_selected_to_end_shortcut)
        self.window.bind("<Control-Shift-D>", lambda _e: self.show_dry_run_preview())
        self.listbox.bind("<Control-Shift-D>", lambda _e: self.show_dry_run_preview())
        self.window.bind("<Control-Alt-d>", lambda _e: self.show_dry_run_preview_with_values())
        self.listbox.bind("<Control-Alt-d>", lambda _e: self.show_dry_run_preview_with_values())
        self.window.bind_all("<Home>", self.move_to_top_shortcut)
        self.window.bind_all("<End>", self.move_to_bottom_shortcut)
        self.listbox.bind("<Home>", self.move_to_top_shortcut)
        self.listbox.bind("<End>", self.move_to_bottom_shortcut)
        self.kind_var.trace_add("write", self.update_kind_ui)
        self.listbox.bind("<<ListboxSelect>>", self.on_select)
        self.update_kind_ui()
        self.refresh()

    def update_kind_ui(self, *_args):
        kind = self.kind_var.get().strip().lower()
        if kind == "vars":
            self.value_label.config(text="Vars JSON:")
            self.hint_var.set('Enter a JSON list, e.g. ["path", "host"]')
        elif kind == "select_profile":
            self.value_label.config(text="Profile:")
            self.hint_var.set("Enter a saved window profile name, e.g. server")
        elif kind == "sleep":
            self.value_label.config(text="Seconds:")
            self.hint_var.set("Enter a number, e.g. 1 or 0.5")
        elif kind == "send":
            self.value_label.config(text="Command:")
            self.value_label.config(text="Command:")
            self.hint_var.set("Plain text command run in a new terminal")
        elif kind == "detached":
            self.value_label.config(text="Command:")
            self.hint_var.set("Plain text detached command run in background")
        else:
            self.value_label.config(text="Value:")
            self.hint_var.set("")

    def build_menu(self):
        menubar = Menu(self.window)

        edit_menu = Menu(menubar, tearoff=0)
        edit_menu.add_command(label="Insert Before\tCtrl+I", command=self.insert_step_before)
        edit_menu.add_command(label="Duplicate Step\tCtrl+D", command=self.duplicate_step)
        edit_menu.add_command(label="Delete Step\tDelete", command=self.delete_step)
        edit_menu.add_separator()
        edit_menu.add_command(label="Move Up\tAlt+Up", command=self.move_up)
        edit_menu.add_command(label="Move Down\tAlt+Down", command=self.move_down)
        edit_menu.add_separator()
        edit_menu.add_command(label="Move To Top\tHome", command=self.move_to_top)
        edit_menu.add_command(label="Move To Bottom\tEnd", command=self.move_to_bottom)
        menubar.add_cascade(label="Edit", menu=edit_menu)

        templates_menu = Menu(menubar, tearoff=0)
        templates_menu.add_command(label="Save Current Chain as Template", command=self.save_steps_as_template)
        templates_menu.add_command(label="Insert Template Before Selected", command=self.insert_template_before_selected)
        templates_menu.add_command(label="Append Template", command=self.append_template)
        templates_menu.add_separator()
        templates_menu.add_command(label="List Templates", command=self.manage_chain_templates)
        menubar.add_cascade(label="Templates", menu=templates_menu)

        run_menu = Menu(menubar, tearoff=0)
        run_menu.add_command(label="Run Selected Step\tCtrl+R", command=self.run_selected_step)
        run_menu.add_command(label="Run To End\tCtrl+Shift+R", command=self.run_from_selected_to_end)
        run_menu.add_separator()
        run_menu.add_command(label="Validate Chain", command=self.validate_chain_with_notice)
        run_menu.add_command(label="Dry Run\tCtrl+Shift+D", command=self.show_dry_run_preview)
        menubar.add_cascade(label="Run", menu=run_menu)

        help_menu = Menu(menubar, tearoff=0)
        help_menu.add_command(label="Shortcuts", command=self.show_chain_builder_shortcuts)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.window.config(menu=menubar)


    def on_drag_start(self, event):
        index = self.listbox.nearest(event.y)
        if index >= 0:
            self.drag_index = index


    def on_drag_motion(self, event):
        if self.drag_index is None:
            return

        new_index = self.listbox.nearest(event.y)

        if new_index == self.drag_index:
            return

        if new_index < 0 or new_index >= len(self.steps):
            return

        # move step
        step = self.steps.pop(self.drag_index)
        self.steps.insert(new_index, step)

        self.refresh()

        self.listbox.selection_clear(0, END)
        self.listbox.selection_set(new_index)
        self.listbox.activate(new_index)
        self.listbox.see(new_index)

        self.drag_index = new_index

    def get_selected_step_index(self):
        idxs = self.listbox.curselection()
        if idxs:
            return idxs[0]

        try:
            active = self.listbox.index("active")
            if 0 <= active < len(self.steps):
                return active
        except Exception:
            pass

        return None


    def move_to_top(self):
        i = self.get_selected_step_index()
        if i is None or i <= 0:
            return

        step = self.steps.pop(i)
        self.steps.insert(0, step)

        self.refresh()
        self.listbox.selection_clear(0, END)
        self.listbox.selection_set(0)
        self.listbox.activate(0)
        self.listbox.see(0)


    def move_to_bottom(self):
        i = self.get_selected_step_index()
        if i is None or i >= len(self.steps) - 1:
            return

        step = self.steps.pop(i)
        self.steps.append(step)

        new_index = len(self.steps) - 1

        self.refresh()
        self.listbox.selection_clear(0, END)
        self.listbox.selection_set(new_index)
        self.listbox.activate(new_index)
        self.listbox.see(new_index)

    def move_to_top_shortcut(self, event=None):
        self.move_to_top()
        return "break"

    def move_to_bottom_shortcut(self, event=None):
        self.move_to_bottom()
        return "break"

    def step_to_label(self, step):
        if isinstance(step, (list, tuple)) and step:
            kind = step[0]
            return f"{kind}: {step!r}"
        return repr(step)

    def show_chain_builder_shortcuts(self):
        messagebox.showinfo(
            "Chain Builder Shortcuts",
            "\n".join([
                "Chain Builder Shortcuts",
                "",
                "Ctrl+I         Insert step before selected",
                "Ctrl+D         Duplicate selected step",
                "Delete         Delete selected step",
                "Alt+Up         Move selected step up",
                "Alt+Down       Move selected step down",
                "Home           Move selected step to top",
                "End            Move selected step to bottom",
                "Ctrl+R         Run selected step",
                "Ctrl+Shift+R   Run selected step to end",
                "Ctrl+Shift+D   Dry run preview",
            ])
        )

    def save_steps_as_template(self):
        if not self.steps:
            messagebox.showerror("Chain Templates", "There are no steps to save.")
            return

        prompt = MultiFieldPrompt(
            self.window,
            "Save Chain Template",
            ["template_name"],
            heading="Enter template name",
        )

        values = prompt.show()
        if values is None:
            return

        name = values.get("template_name", "").strip()
        if not name:
            messagebox.showerror("Chain Templates", "Template name is required.")
            return

        templates = self.app.get_chain_templates()

        if name in templates:
            if not messagebox.askokcancel(
                "Overwrite Template",
                f"Template '{name}' already exists.\n\nOverwrite it?"
            ):
                return

        templates[name] = copy.deepcopy(self.steps)
        self.app.persist_chain_templates()
        self.app.set_status(f"Saved chain template {name}")
        messagebox.showinfo("Chain Templates", f"Saved template:\n\n{name}")


    def choose_chain_template(self):
        templates = self.app.get_chain_templates()
        if not templates:
            messagebox.showerror("Chain Templates", "No chain templates have been saved yet.")
            return None

        names = sorted(templates.keys())

        prompt = MultiFieldPrompt(
            self.window,
            "Choose Chain Template",
            ["template_name"],
            defaults={"template_name": names[0]},
            heading="Enter template name",
        )

        values = prompt.show()
        if values is None:
            return None

        name = values.get("template_name", "").strip()
        if name not in templates:
            available = "\n".join(names)
            messagebox.showerror(
                "Chain Templates",
                f"Unknown template: {name}\n\nAvailable templates:\n{available}"
            )
            return None

        return copy.deepcopy(templates[name])


    def insert_template_before_selected(self):
        steps = self.choose_chain_template()
        if steps is None:
            return

        idxs = self.listbox.curselection()
        insert_index = idxs[0] if idxs else len(self.steps)

        for offset, step in enumerate(steps):
            self.steps.insert(insert_index + offset, step)

        self.refresh()
        self.listbox.selection_clear(0, END)
        self.listbox.selection_set(insert_index)
        self.listbox.activate(insert_index)
        self.listbox.see(insert_index)


    def append_template(self):
        steps = self.choose_chain_template()
        if steps is None:
            return

        start = len(self.steps)
        self.steps.extend(steps)

        self.refresh()
        if self.steps:
            self.listbox.selection_clear(0, END)
            self.listbox.selection_set(start)
            self.listbox.activate(start)
            self.listbox.see(start)


    def manage_chain_templates(self):
        templates = self.app.get_chain_templates()

        if not templates:
            messagebox.showinfo("Chain Templates", "No templates saved yet.")
            return

        lines = ["Saved Chain Templates", ""]

        for name in sorted(templates.keys()):
            steps = templates.get(name, [])
            lines.append(f"{name}  ({len(steps)} step{'s' if len(steps) != 1 else ''})")

        messagebox.showinfo("Chain Templates", "\n".join(lines))

    def refresh(self):
        self.listbox.delete(0, END)
        for step in self.steps:
            self.listbox.insert(END, self.step_to_label(step))

    def insert_step_before(self):
        try:
            step = self.parse_current_step()
        except Exception as exc:
            messagebox.showerror("Chain Builder", str(exc))
            return

        idxs = self.listbox.curselection()

        if idxs:
            insert_index = idxs[0]
        else:
            insert_index = len(self.steps)

        self.steps.insert(insert_index, step)
        self.refresh()

        self.listbox.selection_clear(0, END)
        self.listbox.selection_set(insert_index)
        self.listbox.activate(insert_index)
        self.listbox.see(insert_index)

        self.value_text.delete("1.0", END)
        self.value_text.focus_set()

    def apply_to_editor_now(self):
        errors = self.validate_chain()
        if errors:
            messagebox.showerror("Validate Chain", "\n".join(errors))
            return

        self.result = list(self.steps)

        try:
            self.window.grab_release()
        except Exception:
            pass

        self.window.destroy()

    def validate_chain(self) -> list[str]:
        errors = []

        if not self.steps:
            errors.append("Chain has no steps.")
            return errors

        for index, step in enumerate(self.steps, start=1):
            if not isinstance(step, (list, tuple)) or not step:
                errors.append(f"Step {index}: invalid step format.")
                continue

            kind = step[0]

            if kind == "vars":
                if len(step) < 2 or not isinstance(step[1], list):
                    errors.append(f"Step {index}: vars step must be ['vars', ['name1', 'name2']].")
                else:
                    for var_name in step[1]:
                        if not isinstance(var_name, str) or not var_name.strip():
                            errors.append(f"Step {index}: vars contains an invalid variable name.")

            elif kind == "select_profile":
                if len(step) < 2 or not str(step[1]).strip():
                    errors.append(f"Step {index}: select_profile requires a profile name.")

            elif kind == "sleep":
                if len(step) < 2:
                    errors.append(f"Step {index}: sleep requires seconds.")
                else:
                    try:
                        seconds = float(step[1])
                        if seconds < 0:
                            errors.append(f"Step {index}: sleep seconds cannot be negative.")
                    except Exception:
                        errors.append(f"Step {index}: sleep value must be a number.")

            elif kind in (1, 2, 3, "spawn", "send", "detached"):
                if len(step) < 2 or not str(step[1]).strip():
                    errors.append(f"Step {index}: command step requires command text.")

            else:
                errors.append(f"Step {index}: unknown step kind {kind!r}.")

        return errors


    def validate_chain_with_notice(self):
        errors = self.validate_chain()

        if errors:
            messagebox.showerror("Validate Chain", "\n".join(errors))
            return False

        messagebox.showinfo("Validate Chain", "Chain looks valid.")
        return True


    def run_selected_step(self):
        index = self.get_selected_step_index()

        if index is None:
            messagebox.showerror("Run Selected Step", "Select a step first.")
            return

        if index < 0 or index >= len(self.steps):
            return

        step = self.steps[index]

        try:
            self.app.run_chain_step(step)
            self.app.set_status(f"Ran chain step #{index + 1}")
        except Exception as exc:
            messagebox.showerror(
                "Run Selected Step",
                f"Could not run selected step:\n\n{exc}"
            )


    def run_selected_step_shortcut(self, event=None):
        self.run_selected_step()
        return "break"

    def run_from_selected_to_end(self):
        index = self.get_selected_step_index()

        if index is None:
            messagebox.showerror("Run To End", "Select a step first.")
            return

        if index < 0 or index >= len(self.steps):
            return

        failures = []

        for i in range(index, len(self.steps)):
            step = self.steps[i]

            try:
                self.app.run_chain_step(step)
                self.app.set_status(f"Ran chain step #{i + 1}")
            except Exception as exc:
                failures.append(f"Step {i + 1}: {exc}")
                break

        if failures:
            messagebox.showerror(
                "Run To End",
                "\n".join(failures)
            )


    def run_from_selected_to_end_shortcut(self, event=None):
        self.run_from_selected_to_end()
        return "break"

    def dry_run_lines(self, substitute_vars: bool = False) -> list[str]:
        lines = ["Dry Run Preview", ""]

        if not self.steps:
            lines.append("Chain has no steps.")
            return lines

        values = {}

        if substitute_vars:
            var_names = []
            for step in self.steps:
                if (
                    isinstance(step, (list, tuple))
                    and len(step) >= 2
                    and step[0] == "vars"
                    and isinstance(step[1], list)
                ):
                    for name in step[1]:
                        if isinstance(name, str) and name not in var_names:
                            var_names.append(name)

            if var_names:
                prompt = MultiFieldPrompt(
                    self.window,
                    "Dry Run Variables",
                    var_names,
                    heading="Enter preview values",
                )
                values = prompt.show() or {}

        def substitute(text: str) -> str:
            if not substitute_vars:
                return text
            for key, value in values.items():
                text = text.replace(f"<{key}>", value)
            return text

        for index, step in enumerate(self.steps, start=1):
            if not isinstance(step, (list, tuple)) or not step:
                lines.append(f"{index}. INVALID STEP: {step!r}")
                continue

            kind = step[0]

            if kind == "vars":
                names = step[1] if len(step) > 1 and isinstance(step[1], list) else []
                lines.append(
                    f"{index}. prompt vars -> {', '.join(map(str, names)) if names else '(none)'}"
                )

            elif kind == "select_profile":
                profile = step[1] if len(step) > 1 else ""
                lines.append(f"{index}. select profile -> {profile or '(missing)'}")

            elif kind == "sleep":
                seconds = step[1] if len(step) > 1 else ""
                lines.append(f"{index}. sleep -> {seconds} second(s)")

            elif kind in (1, "spawn"):
                command = substitute(str(step[1])) if len(step) > 1 else ""
                lines.append(f"{index}. spawn terminal -> {command or '(missing command)'}")

            elif kind in (2, "send"):
                command = substitute(str(step[1])) if len(step) > 1 else ""
                lines.append(f"{index}. send to selected window -> {command or '(missing command)'}")

            elif kind in (3, "detached"):
                command = substitute(str(step[1])) if len(step) > 1 else ""
                lines.append(f"{index}. detached/background -> {command or '(missing command)'}")

            else:
                lines.append(f"{index}. UNKNOWN kind={kind!r} step={step!r}")

            if len(step) > 2 and isinstance(step[2], dict) and step[2]:
                lines.append(f"   options -> {step[2]}")

        return lines

    def show_dry_run_preview(self):
        lines = self.dry_run_lines(substitute_vars=False)
        messagebox.showinfo("Dry Run Preview", "\n".join(lines))

    def show_dry_run_preview_with_values(self):
        lines = self.dry_run_lines(substitute_vars=True)
        messagebox.showinfo("Dry Run Preview With Values", "\n".join(lines))

    def parse_current_step(self):
        kind = self.kind_var.get().strip().lower()
        value = self.value_text.get("1.0", END).strip()
        if not kind:
            raise ValueError("Step kind is required.")

        if kind == "vars":
            parsed = json.loads(value)
            if not isinstance(parsed, list):
                raise ValueError("vars value must be a JSON list.")
            return ["vars", parsed]
        if kind == "select_profile":
            if not value:
                raise ValueError("Profile name is required.")
            return ["select_profile", value]
        if kind == "sleep":
            if not value:
                raise ValueError("Sleep seconds are required.")
            try:
                num = int(value)
            except ValueError:
                num = float(value)
            return ["sleep", num]
        if kind == "send":
            return [2, value]
        if kind == "spawn":
            return [1, value]
        if kind == "detached":
            return [3, value]
        raise ValueError("Unknown step kind.")

    def add_or_update_step(self):
        try:
            step = self.parse_current_step()
        except Exception as exc:
            messagebox.showerror("Chain Builder", str(exc))
            return
        idxs = self.listbox.curselection()
        if idxs:
            self.steps[idxs[0]] = step
        else:
            self.steps.append(step)
        self.refresh()

    def duplicate_step(self):
        idxs = self.listbox.curselection()
        if not idxs:
            return
        step = self.steps[idxs[0]]
        cloned = json.loads(json.dumps(step))
        self.steps.insert(idxs[0] + 1, cloned)
        self.refresh()
        self.listbox.selection_set(idxs[0] + 1)

    def delete_step(self):
        idxs = self.listbox.curselection()
        if not idxs:
            return
        del self.steps[idxs[0]]
        self.refresh()

    def move_up(self):
        idxs = self.listbox.curselection()
        if not idxs or idxs[0] == 0:
            return
        i = idxs[0]
        self.steps[i-1], self.steps[i] = self.steps[i], self.steps[i-1]
        self.refresh()
        self.listbox.selection_set(i-1)

    def move_down(self):
        idxs = self.listbox.curselection()
        if not idxs or idxs[0] >= len(self.steps) - 1:
            return
        i = idxs[0]
        self.steps[i+1], self.steps[i] = self.steps[i], self.steps[i+1]
        self.refresh()
        self.listbox.selection_set(i+1)

    def validate_chain(self) -> list[str]:
        errors = []

        if not self.steps:
            errors.append("Chain has no steps.")
            return errors

        for index, step in enumerate(self.steps, start=1):
            if not isinstance(step, (list, tuple)) or not step:
                errors.append(f"Step {index}: invalid step format.")
                continue

            kind = step[0]

            if kind == "vars":
                if len(step) < 2 or not isinstance(step[1], list):
                    errors.append(f"Step {index}: vars step must be ['vars', ['name1', 'name2']].")
                else:
                    for var_name in step[1]:
                        if not isinstance(var_name, str) or not var_name.strip():
                            errors.append(f"Step {index}: vars contains an invalid variable name.")

            elif kind == "select_profile":
                if len(step) < 2 or not str(step[1]).strip():
                    errors.append(f"Step {index}: select_profile requires a profile name.")

            elif kind == "sleep":
                if len(step) < 2:
                    errors.append(f"Step {index}: sleep requires seconds.")
                else:
                    try:
                        seconds = float(step[1])
                        if seconds < 0:
                            errors.append(f"Step {index}: sleep seconds cannot be negative.")
                    except Exception:
                        errors.append(f"Step {index}: sleep value must be a number.")

            elif kind in (1, 2, 3, "spawn", "send", "detached"):
                if len(step) < 2 or not str(step[1]).strip():
                    errors.append(f"Step {index}: command step requires command text.")

            else:
                errors.append(f"Step {index}: unknown step kind {kind!r}.")

        return errors


    def validate_chain_with_notice(self):
        errors = self.validate_chain()

        if errors:
            messagebox.showerror("Validate Chain", "\n".join(errors))
            return False

        messagebox.showinfo("Validate Chain", "Chain looks valid.")
        return True

    def on_select(self, _event=None):
        self.load_selected()

    def load_selected(self):
        idxs = self.listbox.curselection()
        if not idxs:
            return
        step = self.steps[idxs[0]]
        self.value_text.delete("1.0", END)
        if isinstance(step, (list, tuple)) and step:
            if step[0] == "vars":
                self.kind_var.set("vars")
                self.value_text.insert("1.0", json.dumps(step[1], indent=2))
            elif step[0] == "select_profile":
                self.kind_var.set("select_profile")
                self.value_text.insert("1.0", str(step[1]))
            elif step[0] == "sleep":
                self.kind_var.set("sleep")
                self.value_text.insert("1.0", str(step[1]))
            elif step[0] == 2:
                self.kind_var.set("send")
                self.value_text.insert("1.0", str(step[1]))
            elif step[0] == 1:
                self.kind_var.set("spawn")
                self.value_text.insert("1.0", str(step[1]))
            elif step[0] == 3:
                self.kind_var.set("detached")
                self.value_text.insert("1.0", str(step[1]))
        self.update_kind_ui()

    def apply_and_close(self):
        self.result = list(self.steps)
        self.window.destroy()

    def close(self):
        self.result = None
        self.window.destroy()

    def show(self):
        self.parent.wait_window(self.window)
        return self.result


class CommandEditorWindow:
    def __init__(self, app):
        self.app = app
        self.window = Toplevel(app.root)
        self.window.title("Command / Chain Editor")
        self.window.geometry("1040x700")
        self.window.transient(app.root)

        outer = Frame(self.window, padx=8, pady=8)
        outer.pack(fill=BOTH, expand=True)

        Label(
            outer,
            text="Command / Chain Editor",
            bd=4,
            width=34,
            bg="lightgreen",
            fg="black",
            relief="raised",
        ).pack(pady=(0, 8))

        action_row = Frame(outer)
        action_row.pack(fill=X, pady=(0, 8))
        Button(action_row, text="Save Entry", width=16, bg="darkgreen", fg="white", command=self.save_entry).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Delete Entry", width=16, bg="#7f6000", fg="white", command=self.delete_entry).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="New / Clear", width=16, bg="#555555", fg="white", command=self.clear_form).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Refresh List", width=16, bg="navy", fg="white", command=self.refresh).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Close", width=16, bg="red", fg="black", command=self.window.destroy).pack(side=RIGHT)

        top = Frame(outer)
        top.pack(fill=BOTH, expand=True)

        left = Frame(top)
        left.pack(side=LEFT, fill=Y)

        right = Frame(top)
        right.pack(side=RIGHT, fill=BOTH, expand=True, padx=(10, 0))

        self.listbox = Listbox(left, width=42, height=26)
        self.listbox.pack(side=LEFT, fill=Y)
        scrollbar = Scrollbar(left, command=self.listbox.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.listbox.config(yscrollcommand=scrollbar.set)

        form = Frame(right)
        form.pack(fill=X)

        Label(form, text="Category:", width=14, anchor="w").grid(row=0, column=0, sticky="w", pady=3)
        self.category_var = StringVar()
        Entry(form, textvariable=self.category_var, width=42).grid(row=0, column=1, sticky="ew", pady=3)

        Label(form, text="Command Name:", width=14, anchor="w").grid(row=1, column=0, sticky="w", pady=3)
        self.name_var = StringVar()
        Entry(form, textvariable=self.name_var, width=42).grid(row=1, column=1, sticky="ew", pady=3)

        Label(form, text="Type:", width=14, anchor="w").grid(row=2, column=0, sticky="w", pady=3)
        self.type_var = StringVar(value="2")
        self.type_entry = Entry(form, textvariable=self.type_var, width=42)
        self.type_entry.grid(row=2, column=1, sticky="ew", pady=3)

        self.command_label = Label(form, text="Command:", width=14, anchor="nw")
        self.command_label.grid(row=3, column=0, sticky="nw", pady=3)
        self.command_text = Text(form, height=14, width=70, wrap="word")
        self.command_text.grid(row=3, column=1, sticky="nsew", pady=3)

        builder_row = Frame(form)
        builder_row.grid(row=4, column=1, sticky="w", pady=(0, 6))
        self.builder_button = Button(builder_row, text="Visual Chain Builder", bg="#2f5597", fg="white", command=self.open_chain_builder)
        self.builder_button.pack(side=LEFT)
        self.chain_hint = Label(builder_row, text="Use this for type = chain", fg="#333333")
        self.chain_hint.pack(side=LEFT, padx=(8, 0))

        Label(form, text="Options JSON:", width=14, anchor="nw").grid(row=5, column=0, sticky="nw", pady=3)
        self.options_text = Text(form, height=5, width=70, wrap="word")
        self.options_text.grid(row=5, column=1, sticky="nsew", pady=3)

        form.grid_columnconfigure(1, weight=1)

        help_box = Text(right, height=11, wrap="word")
        help_box.pack(fill=BOTH, expand=True, pady=(10, 0))
        help_box.insert(
            "1.0",
            "Simple command:\n"
            "  Type: 2\n"
            "  Command: pwd\n\n"
            "Detached command:\n"
            "  Type: 3\n"
            "  Command: code > /dev/null 2>&1 &\n\n"
            "Chain:\n"
            "  Type: chain\n"
            "  Use the Visual Chain Builder button\n\n"
            "Options JSON example:\n"
            "  {\"confirm\": true}\n"
        )
        help_box.config(state="disabled")

        self.type_choices = {
            "Select Window": "0",
            "Spawn Terminal": "1",
            "Send To Window": "2",
            "Detached Command": "3",
            "Chain": "chain",
            "Plugin": "plugin",
        }

        self.snapshot = []
        self.listbox.bind("<<ListboxSelect>>", self.on_select)
        self.type_var.trace_add("write", self.update_type_ui)
        self.refresh()
        self.clear_form()

    def update_type_ui(self, *_args):
        cmd_type_raw = self.type_var.get().strip().lower()
        if cmd_type_raw == "chain":
            self.command_label.config(text="Chain JSON:")
            self.builder_button.config(state="normal")
            self.chain_hint.config(text="Build visually or edit JSON directly")
        else:
            self.command_label.config(text="Command:")
            self.builder_button.config(state="disabled")
            self.chain_hint.config(text="Plain text command for normal entries")

    def open_chain_builder(self):
        current = self.command_text.get("1.0", END).strip()
        initial = []

        if current:
            try:
                initial = json.loads(current)
            except Exception as exc:
                messagebox.showerror(
                    "Chain Builder",
                    f"Could not parse current chain JSON:\n\n{exc}"
                )
                return

        builder = ChainBuilderWindow(self.window, self.app, initial_steps=initial)
        result = builder.show()

        if result is not None:
            self.command_text.delete("1.0", END)
            self.command_text.insert("1.0", json.dumps(result, indent=2))


    def refresh(self):
        self.snapshot.clear()
        self.listbox.delete(0, END)
        categories = getattr(self.app.cfg, "Categories", {})
        for category in sorted(categories.keys()):
            commands = categories.get(category, {})
            if not isinstance(commands, dict):
                continue
            for name in sorted(commands.keys()):
                entry = commands[name]
                self.snapshot.append((category, name, entry))
                self.listbox.insert(END, f"{category} -> {name}")

    def on_select(self, _event=None):
        idxs = self.listbox.curselection()
        if not idxs:
            return
        category, name, entry = self.snapshot[idxs[0]]
        self.category_var.set(category)
        self.name_var.set(name)
        cmd_type, cmd, options = self.app.parse_command_entry_public(entry)
        self.type_var.set(str(cmd_type))
        self.command_text.delete("1.0", END)
        if isinstance(cmd, str):
            self.command_text.insert("1.0", cmd)
        else:
            self.command_text.insert("1.0", json.dumps(cmd, indent=2))
        self.options_text.delete("1.0", END)
        self.options_text.insert("1.0", json.dumps(options, indent=2) if options else "{}")
        self.update_type_ui()

    def clear_form(self):
        try:
            if hasattr(self, "category_choices") and self.category_choices:
                self.category_var.set(self.category_choices[0])
            else:
                self.category_var.set("")

            self.name_var.set("")

            if hasattr(self, "type_var"):
                self.type_var.set("Send To Window")

            if hasattr(self, "command_text") and self.command_text.winfo_exists():
                self.command_text.delete("1.0", END)

            if hasattr(self, "options_text") and self.options_text.winfo_exists():
                self.options_text.delete("1.0", END)
                self.options_text.insert("1.0", "{}")

            self.update_type_ui()
        except Exception:
            pass

    def _parse_form(self):
        category = self.category_var.get().strip()
        name = self.name_var.get().strip()
        cmd_type_raw = self.type_choices.get(self.type_var.get(), self.type_var.get()).strip()
        command_raw = self.command_text.get("1.0", END).strip()
        options_raw = self.options_text.get("1.0", END).strip() or "{}"

        if not category or not name or not cmd_type_raw:
            raise ValueError("Category, command name, and type are required.")

        if cmd_type_raw.lower() == "chain":
            cmd_type = "chain"
            command = json.loads(command_raw) if command_raw else []
            if not isinstance(command, list):
                raise ValueError("Chain JSON must decode to a list.")
        elif cmd_type_raw.lower() == "plugin":
            cmd_type = "plugin"
            command = command_raw
        else:
            try:
                cmd_type = int(cmd_type_raw)
            except ValueError:
                cmd_type = cmd_type_raw
            command = command_raw

        options = json.loads(options_raw) if options_raw else {}
        if not isinstance(options, dict):
            raise ValueError("Options JSON must decode to an object/dict.")
        return category, name, [cmd_type, command, options]

    def save_entry(self):
        try:
            category, name, entry = self._parse_form()
        except Exception as exc:
            messagebox.showerror("Command Editor", str(exc))
            return

        categories = getattr(self.app.cfg, "Categories", None)
        if categories is None or not isinstance(categories, dict):
            categories = {}
            setattr(self.app.cfg, "Categories", categories)

        if category not in categories or not isinstance(categories.get(category), dict):
            categories[category] = {}

        categories[category][name] = entry
        self.app.persist_categories()
        self.app.rebuild_category_buttons()
        self.app.set_status(f"Saved command {category}/{name}")

        try:
            if self.window.winfo_exists():
                if hasattr(self, "listbox") and self.listbox.winfo_exists():
                    self.refresh()
        except Exception:
            pass

    def delete_entry(self):
        category = self.category_var.get().strip()
        name = self.name_var.get().strip()
        categories = getattr(self.app.cfg, "Categories", {})

        if category not in categories or name not in categories[category]:
            messagebox.showerror("Command Editor", "Selected command was not found.")
            return

        del categories[category][name]
        if not categories[category]:
            del categories[category]

        self.app.persist_categories()
        self.app.rebuild_category_buttons()
        self.app.set_status(f"Deleted command {category}/{name}")

        try:
            if self.window.winfo_exists():
                if hasattr(self, "listbox") and self.listbox.winfo_exists():
                    self.refresh()
        except Exception:
            pass

    def load_command(self, category: str, name: str) -> None:
        categories = getattr(self.app.cfg, "Categories", {})

        if category not in categories or name not in categories[category]:
            messagebox.showerror(
                "Command Editor",
                f"Command not found: {category}/{name}"
            )
            return

        entry = categories[category][name]

        self.category_var.set(category)
        self.name_var.set(name)

        cmd_type, cmd, options = self.app.parse_command_entry_public(entry)

        reverse_type_choices = {v: k for k, v in self.type_choices.items()}
        self.type_var.set(reverse_type_choices.get(str(cmd_type), "Send To Window"))

        self.command_text.delete("1.0", END)
        if isinstance(cmd, str):
            self.command_text.insert("1.0", cmd)
        else:
            self.command_text.insert("1.0", json.dumps(cmd, indent=2))

        self.options_text.delete("1.0", END)
        self.options_text.insert("1.0", json.dumps(options, indent=2) if options else "{}")

        self.update_type_ui()


class CategoryEditorWindow:
    def __init__(self, app):
        self.app = app
        self.window = Toplevel(app.root)
        self.window.title("Category Editor")
        self.window.geometry("860x520")
        self.window.transient(app.root)

        outer = Frame(self.window, padx=8, pady=8)
        outer.pack(fill=BOTH, expand=True)

        Label(
            outer,
            text="Category Editor",
            bd=4,
            width=30,
            bg="lightgreen",
            fg="black",
            relief="raised",
        ).pack(pady=(0, 8))

        action_row = Frame(outer)
        action_row.pack(fill=X, pady=(0, 8))
        Button(action_row, text="Create Category", width=16, bg="darkgreen", fg="white", command=self.create_category).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Rename Category", width=16, bg="#2f5597", fg="white", command=self.rename_category).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Delete Category", width=16, bg="#7f6000", fg="white", command=self.delete_category).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Refresh", width=16, bg="navy", fg="white", command=self.refresh).pack(side=LEFT, padx=(0, 6))
        Button(action_row, text="Close", width=16, bg="red", fg="black", command=self.window.destroy).pack(side=RIGHT)

        body = Frame(outer)
        body.pack(fill=BOTH, expand=True)

        left = Frame(body)
        left.pack(side=LEFT, fill=Y)

        right = Frame(body)
        right.pack(side=RIGHT, fill=BOTH, expand=True, padx=(10, 0))

        self.listbox = Listbox(left, width=38, height=22)
        self.listbox.pack(side=LEFT, fill=Y)
        scrollbar = Scrollbar(left, command=self.listbox.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.listbox.config(yscrollcommand=scrollbar.set)

        self.info = Text(right, wrap="word", width=60, height=22)
        self.info.pack(fill=BOTH, expand=True)

        self.listbox.bind("<<ListboxSelect>>", self.show_selected)
        self.refresh()

    def get_categories(self):
        categories = getattr(self.app.cfg, "Categories", {})
        if not isinstance(categories, dict):
            categories = {}
            setattr(self.app.cfg, "Categories", categories)
        return categories

    def refresh(self):
        self.listbox.delete(0, END)
        categories = self.get_categories()
        self.snapshot = []
        for name in sorted(categories.keys()):
            commands = categories.get(name, {})
            count = len(commands) if isinstance(commands, dict) else 0
            self.snapshot.append((name, count))
            self.listbox.insert(END, f"{name} ({count} command{'s' if count != 1 else ''})")
        self.info.delete("1.0", END)
        self.info.insert("1.0", "Select a category to inspect.\n")

    def show_selected(self, _event=None):
        item = self.selected_item()

        self.info.delete("1.0", END)

        if not item:
            return

        lines = [
            f'Category: {item["category"]}',
            f'Command: {item["name"]}',
            f'Type: {item["type"]}',
            f'Usage: {item.get("usage_count", 0)}',
            "",
            "Preview:",
            item["preview"],
        ]

        self.info.insert("1.0", "\n".join(lines))

    def selected_category_name(self):
        idxs = self.listbox.curselection()
        if not idxs:
            return None
        return self.snapshot[idxs[0]][0]

    def create_category(self):
        prompt = MultiFieldPrompt(
            self.window,
            "Create Category",
            ["category_name"],
            heading="Enter a new category name",
        )
        values = prompt.show()
        if values is None:
            return
        name = values.get("category_name", "").strip()
        if not name:
            messagebox.showerror("Category Editor", "Category name is required.")
            return
        categories = self.get_categories()
        if name in categories:
            messagebox.showerror("Category Editor", f"Category already exists: {name}")
            return
        categories[name] = {}
        self.app.persist_categories()
        self.app.rebuild_category_buttons()
        self.app.set_status(f"Created category {name}")
        self.refresh()

    def rename_category(self):
        old_name = self.selected_category_name()
        if not old_name:
            messagebox.showerror("Category Editor", "Select a category to rename.")
            return
        prompt = MultiFieldPrompt(
            self.window,
            "Rename Category",
            ["new_name"],
            defaults={"new_name": old_name},
            heading=f"Rename category '{old_name}'",
        )
        values = prompt.show()
        if values is None:
            return
        new_name = values.get("new_name", "").strip()
        if not new_name:
            messagebox.showerror("Category Editor", "New category name is required.")
            return
        categories = self.get_categories()
        if new_name != old_name and new_name in categories:
            messagebox.showerror("Category Editor", f"Category already exists: {new_name}")
            return
        categories[new_name] = categories.pop(old_name)
        self.app.persist_categories()
        self.app.rebuild_category_buttons()
        self.app.set_status(f"Renamed category {old_name} -> {new_name}")
        self.refresh()

    def delete_category(self):
        name = self.selected_category_name()
        if not name:
            messagebox.showerror("Category Editor", "Select a category to delete.")
            return
        categories = self.get_categories()
        commands = categories.get(name, {})
        if isinstance(commands, dict) and commands:
            messagebox.showerror(
                "Category Editor",
                "Category is not empty. Delete or move its commands first.",
            )
            return
        if not messagebox.askokcancel("Delete Category", f"Delete empty category '{name}'?"):
            return
        del categories[name]
        self.app.persist_categories()
        self.app.rebuild_category_buttons()
        self.app.set_status(f"Deleted category {name}")
        self.refresh()


class CommandPaletteWindow:
    def __init__(self, app):
        self.app = app
        self.window = Toplevel(app.root)
        self.window.title("Command Palette")
        self.window.geometry("860x520")
        self.window.transient(app.root)
        self.window.resizable(True, True)

        outer = Frame(self.window, padx=8, pady=8)
        outer.pack(fill=BOTH, expand=True)

        Label(
            outer,
            text="Command Palette",
            bd=4,
            width=28,
            bg="lightgreen",
            fg="black",
            relief="raised",
        ).pack(pady=(0, 8))

        search_row = Frame(outer)
        search_row.pack(fill=X, pady=(0, 8))
        Label(search_row, text="Search:", width=10, anchor="w").pack(side=LEFT)

        self.query_var = StringVar()
        self.search_entry = Entry(search_row, textvariable=self.query_var, width=48)
        self.search_entry.pack(side=LEFT, fill=X, expand=True)

        Button(search_row, text="Run", width=10, bg="darkgreen", fg="white", command=self.run_selected).pack(side=LEFT, padx=(6, 0))
        Button(search_row, text="Close", width=10, bg="red", fg="black", command=self.window.destroy).pack(side=LEFT, padx=(6, 0))

        body = Frame(outer)
        body.pack(fill=BOTH, expand=True)

        left = Frame(body)
        left.pack(side=LEFT, fill=BOTH, expand=True)

        self.listbox = Listbox(left, width=48, height=18)
        self.listbox.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar = Scrollbar(left, command=self.listbox.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.listbox.config(yscrollcommand=scrollbar.set)

        self.info = Text(body, wrap="word", width=52, height=18)
        self.info.pack(side=RIGHT, fill=BOTH, expand=True, padx=(10, 0))

        self.snapshot = []
        self.filtered = []

        self.query_var.trace_add("write", self.refresh)
        self.search_entry.bind("<Return>", lambda _e: self.run_selected())
        self.search_entry.bind("<Down>", self.focus_listbox)
        self.listbox.bind("<<ListboxSelect>>", self.show_selected)
        self.listbox.bind("<Double-Button-1>", lambda _e: self.run_selected())
        self.listbox.bind("<Return>", lambda _e: self.run_selected())
        self.window.bind("<Escape>", lambda _e: self.window.destroy())
        self.window.bind("<Control-e>", self.edit_selected)
        self.window.bind("<Control-E>", self.edit_selected)
        self.listbox.bind("<Control-e>", self.edit_selected)
        self.listbox.bind("<Control-E>", self.edit_selected)
        self.window.bind("<Control-d>", self.duplicate_selected)
        self.window.bind("<Control-D>", self.duplicate_selected)
        self.listbox.bind("<Control-d>", self.duplicate_selected)
        self.listbox.bind("<Control-D>", self.duplicate_selected)
        self.window.bind("<Control-f>", self.toggle_favorite_selected)
        self.window.bind("<Control-F>", self.toggle_favorite_selected)
        self.listbox.bind("<Control-f>", self.toggle_favorite_selected)
        self.listbox.bind("<Control-F>", self.toggle_favorite_selected)
        self.window.bind("<Delete>", self.delete_selected)
        self.listbox.bind("<Delete>", self.delete_selected)
        self.window.bind("<F2>", self.rename_selected)
        self.listbox.bind("<F2>", self.rename_selected)

        self.refresh()
        self.search_entry.focus_set()


    def fuzzy_match_score(self, query: str, text: str):
        query = query.strip().lower()
        text = text.lower()

        if not query:
            return 0

        # best case: exact match
        if query == text:
            return 0

        # very good: prefix match
        if text.startswith(query):
            return 1

        # good: substring match
        idx = text.find(query)
        if idx != -1:
            return 10 + idx

        # fallback: subsequence match
        pos = -1
        gap_penalty = 0
        first_idx = None

        for ch in query:
            idx = text.find(ch, pos + 1)
            if idx == -1:
                return None
            if first_idx is None:
                first_idx = idx
            if pos != -1:
                gap_penalty += idx - pos - 1
            pos = idx

        return 100 + gap_penalty + (first_idx or 0)

    def item_match_score(self, query: str, item: dict):
        query = query.strip().lower()
        if not query:
            return 0

        terms = [term for term in query.split() if term]
        if not terms:
            return 0

        total_score = 0

        for term in terms:
            name_score = self.fuzzy_match_score(term, item["name"])
            category_score = self.fuzzy_match_score(term, item["category"])
            preview_score = self.fuzzy_match_score(term, item["preview"])

            candidates = []

            if name_score is not None:
                candidates.append(name_score)

            if category_score is not None:
                candidates.append(1000 + category_score)

            if preview_score is not None:
                candidates.append(2000 + preview_score)

            if not candidates:
                return None

            total_score += min(candidates)

        return total_score

    def section_label_for_item(self, item):
        if item.get("favorite"):
            return "★ Favorites"
        if item.get("recent"):
            return "⟳ Recent"
        return "All Commands"

    def collect_commands(self):
        items = []
        categories = getattr(self.app.cfg, "Categories", {})
        favorites = set((c, s) for c, s in self.app.get_favorites())
        recent_list = self.app.get_recent()
        recent = {(c, s): i for i, (c, s) in enumerate(recent_list)}
        usage = self.app.get_usage()

        for category in sorted(categories.keys()):
            commands = categories.get(category, {})
            if not isinstance(commands, dict):
                continue

            for name in sorted(commands.keys()):
                entry = commands[name]
                try:
                    cmd_type, cmd, options = self.app.parse_command_entry_public(entry)
                except Exception:
                    cmd_type, cmd, options = "?", repr(entry), {}

                preview = cmd if isinstance(cmd, str) else str(cmd)
                is_favorite = (category, name) in favorites
                is_recent = (category, name) in recent
                recent_rank = recent.get((category, name), 999)
                usage_count = int(usage.get(f"{category}/{name}", 0))

                items.append({
                    "category": category,
                    "name": name,
                    "entry": entry,
                    "type": cmd_type,
                    "preview": preview,
                    "options": options,
                    "favorite": is_favorite,
                    "recent": is_recent,
                    "recent_rank": recent_rank,
                    "usage_count": usage_count,
                    "search_blob": f"{category} {name} {preview}".lower(),
                })

        items.sort(
            key=lambda item: (
                not item["favorite"],
                not item["recent"],
                item["recent_rank"],
                -item["usage_count"],
                item["category"].lower(),
                item["name"].lower(),
            )
        )
        return items

    def refresh(self, *_args):
        query = self.query_var.get().strip().lower()
        self.snapshot = self.collect_commands()

        if query:
            scored = []
            for item in self.snapshot:
                score = self.item_match_score(query, item)
                if score is not None:
                    enriched = dict(item)
                    enriched["match_score"] = score
                    scored.append(enriched)

            scored.sort(
                key=lambda item: (
                    not item.get("favorite", False),
                    not item.get("recent", False),
                    item.get("match_score", 999),
                    item.get("recent_rank", 999),
                    item.get("usage_count", 0),
                    item.get("category", "").lower(),
                    item.get("name", "").lower(),
                )
            )
            self.filtered = scored
        else:
            self.filtered = list(self.snapshot)

        self.listbox.delete(0, END)
        self.list_rows = []

        def add_spacer():
            self.listbox.insert(END, "")
            self.list_rows.append(None)

        def add_header(title: str):
            if self.listbox.size() > 0:
                add_spacer()

            self.listbox.insert(END, title)
            header_index = self.listbox.size() - 1
            self.listbox.itemconfig(header_index, fg="blue", bg="#eeeeee")
            self.list_rows.append(None)

        def add_command(item: dict):
            if item.get("favorite"):
                prefix = "★ "
            elif item.get("recent"):
                prefix = "⟳ "
            else:
                prefix = "  "

            usage = item.get("usage_count", 0)

            if item.get("favorite"):
                suffix = ""
            else:
                suffix = f"  ({usage})" if usage > 0 else ""

            self.listbox.insert(END, f'{prefix}{item["category"]} -> {item["name"]}{suffix}')
            self.list_rows.append(item)

        favorites = [i for i in self.filtered if i.get("favorite")]

        recents = [
            i for i in self.filtered
            if i.get("recent")
            and not i.get("favorite")
            and i.get("usage_count", 0) == 0
        ]

        most_used = sorted(
            [
                i for i in self.filtered
                if i.get("usage_count", 0) > 0
                and not i.get("favorite")
            ],
            key=lambda x: -x.get("usage_count", 0)
        )

        all_items = [
            i for i in self.filtered
            if not i.get("favorite")
            and not i.get("recent")
            and i.get("usage_count", 0) == 0
        ]

        if favorites:
            add_header("★ Favorites")
            for item in favorites:
                add_command(item)

        if recents:
            add_header("⟳ Recent")
            for item in recents:
                add_command(item)

        if most_used:
            add_header("🔥 Most Used")
            for item in most_used[:10]:
                add_command(item)

        if all_items:
            add_header("All Commands")
            for item in all_items:
                add_command(item)

        self.info.delete("1.0", END)

        if not any(row is not None for row in self.list_rows):
            self.info.insert("1.0", "No matching commands found.\n")
            return

        self.select_first_command_row()

    def select_first_command_row(self):
        self.listbox.selection_clear(0, END)

        for index in range(self.listbox.size()):
            if index in getattr(self, "list_index_to_item", {}):
                self.listbox.selection_set(index)
                self.listbox.activate(index)
                self.show_selected()
                return

    def selected_item(self):
        idxs = self.listbox.curselection()
        if not idxs:
            return None

        index = idxs[0]

        if not hasattr(self, "list_rows"):
            return None

        if index < 0 or index >= len(self.list_rows):
            return None

        return self.list_rows[index]

    def focus_listbox(self, _event=None):
        if self.listbox.size() > 0:
            self.listbox.focus_set()
            self.select_first_command_row()
        return "break"

    def show_selected(self, _event=None):
        item = self.selected_item()
        self.info.delete("1.0", END)
        if not item:
            return
        lines = [
            f'Category: {item["category"]}',
            f'Command: {item["name"]}',
            f'Type: {item["type"]}',
            "",
            "Preview:",
            item["preview"],
            "",
            "Shortcuts:",
            "  Enter      -> Run command",
            "  Ctrl+E     -> Edit command",
            "  Ctrl+D     -> Duplicate command",
            "  Ctrl+F     -> Toggle favorite",
            "  F2         -> Rename command",
            "  Delete     -> Delete command",
            "  Escape     -> Close palette",
        ]
        self.info.insert("1.0", "\n".join(lines))

    def toggle_favorite_selected(self, event=None):
        item = self.selected_item()

        if not item:
            return "break"

        category = item["category"]
        name = item["name"]

        if item.get("favorite"):
            self.app.remove_favorite(category, name)
            self.app.set_status(f"Removed favorite {category}/{name}")
        else:
            self.app.add_favorite(category, name)
            self.app.set_status(f"Added favorite {category}/{name}")

        self.app.rebuild_favorites_bar()
        self.refresh()

        return "break"

    def run_selected(self):
        item = self.selected_item()
        if not item:
            return
        self.window.destroy()
        self.app.set_status(f'Palette run: {item["category"]}/{item["name"]}')
        self.app.select_cmd(None, item["category"], item["name"])

    def edit_selected(self, event=None):
        item = self.selected_item()

        if not item:
            return "break"

        self.window.destroy()

        editor = CommandEditorWindow(self.app)
        editor.load_command(item["category"], item["name"])

        return "break"

    def duplicate_selected(self, event=None):
        item = self.selected_item()

        if not item:
            return "break"

        self.app.duplicate_command(
            item["category"],
            item["name"]
        )

        self.refresh()
        self.app.set_status(
            f'Duplicated {item["category"]}/{item["name"]}'
        )

        return "break"

    def delete_selected(self, event=None):
        item = self.selected_item()

        if not item:
            return "break"

        category = item["category"]
        name = item["name"]

        if not messagebox.askokcancel(
            "Delete Command",
            f"Delete command '{category}/{name}'?"
        ):
            return "break"

        self.app.delete_command(category, name)
        self.refresh()
        self.app.set_status(f"Deleted command {category}/{name}")

        return "break"

    def rename_selected(self, event=None):
        item = self.selected_item()

        if not item:
            return "break"

        category = item["category"]
        old_name = item["name"]

        prompt = MultiFieldPrompt(
            self.window,
            "Rename Command",
            ["new_name"],
            defaults={"new_name": old_name},
            heading=f"Rename {category}/{old_name}",
        )

        values = prompt.show()
        if values is None:
            return "break"

        new_name = values.get("new_name", "").strip()
        if not new_name:
            messagebox.showerror("Rename Command", "New command name is required.")
            return "break"

        self.app.rename_command(category, old_name, new_name)
        self.refresh()
        self.app.set_status(f"Renamed command {category}/{old_name} -> {new_name}")

        return "break"

class TermForgeApp:
    def __init__(self, root: Tk, cfg) -> None:
        self.root = root
        self.cfg = cfg
        self.root.title(f"{APP_NAME} {APP_VERSION}")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.window_id: int | str | None = None
        self.last_window_id: int | str | None = None
        self.command_history: list[dict] = []
        self.plugins: dict[str, object] = {}
        self.plugin_mtimes: dict[str, float] = {}
        self.plugin_errors: dict[str, str] = {}
        self.debug = bool(getattr(cfg, "debug", {}).get("Flag", False))
        self.application = getattr(cfg, "terminal", {}).get("application", "gnome-terminal")
        self.status_var = StringVar(value="Ready.")
        self.search_var = StringVar()
        self.category_buttons: dict[str, Button] = {}
        self.hotkey_listener = None
        self.hotkeys_enabled = False
        self.hotkey_status = "Hotkeys not initialized."

        if self.debug:
            logging.getLogger().setLevel(logging.DEBUG)

        self.load_state()
        self.log("Starting TermForge")
        self.load_plugins(force=True)
        self.build_main()
        self.bind_global_shortcuts()
        self.initialize_hotkeys()
        self.root.after(250, self.safe_initial_select)

    def log(self, message: str) -> None:
        if self.debug:
            print(message)
        logging.info(message)

    def set_status(self, message: str) -> None:
        self.status_var.set(message)
        self.log(message)

    def show_error(self, title: str, message: str) -> None:
        messagebox.showerror(title, message)

    def load_state(self) -> None:
        self.last_window_id = None
        self.command_history = []
        if not STATE_FILE.exists():
            return
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            self.last_window_id = data.get("last_window_id")
            history = data.get("command_history", [])
            if isinstance(history, list):
                self.command_history = history[:MAX_HISTORY]
        except Exception as exc:
            self.log(f"Could not load state file: {exc}")

    def save_state(self) -> None:
        try:
            payload = {
                "last_window_id": self.window_id if self.window_id is not None else self.last_window_id,
                "command_history": self.command_history[:MAX_HISTORY],
            }
            STATE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as exc:
            self.log(f"Could not save state file: {exc}")

    def on_close(self) -> None:
        self.save_state()
        self.log("Shutting down TermForge")
        try:
            if self.hotkey_listener is not None:
                try:
                    self.hotkey_listener.stop()
                except Exception:
                    pass
            self.root.quit()
        finally:
            self.root.destroy()

    def add_history_entry(self, action_type, command_text, source="manual") -> None:
        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "action_type": str(action_type),
            "command": str(command_text),
            "window_id": self.window_id,
            "source": source,
        }
        self.command_history.insert(0, entry)
        self.command_history = self.command_history[:MAX_HISTORY]
        self.save_state()

    def remember_window(self, window_id) -> None:
        self.window_id = window_id
        self.last_window_id = window_id
        self.save_state()

    def run_chain_step(self, step):
        if not isinstance(step, (list, tuple)) or not step:
            raise ValueError("Invalid chain step.")

        kind = step[0]

        if kind == "sleep":
            import time
            time.sleep(float(step[1]))
            return

        if kind == "select_profile":
            self.select_profile(step[1])
            return

        if kind == "vars":
            return

        if len(step) == 2:
            cmd_type = step[0]
            cmd = step[1]
            options = {}
        else:
            cmd_type = step[0]
            cmd = step[1]
            options = step[2] if len(step) > 2 else {}

        self.run_cmd(cmd_type, cmd, options, None)

    def get_chain_templates(self) -> dict:
        templates = getattr(self.cfg, "ChainTemplates", {})
        if not isinstance(templates, dict):
            templates = {}
            setattr(self.cfg, "ChainTemplates", templates)
        return templates


    def persist_chain_templates(self) -> None:
        self.persist_full_config()

    def get_favorites(self) -> list[tuple[str, str]]:
        favs = []
        raw = getattr(self.cfg, "Favorites", [])
        if not isinstance(raw, list):
            return favs
        for item in raw:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                category, subcategory = item[0], item[1]
                if category in getattr(self.cfg, "Categories", {}) and subcategory in self.cfg.Categories[category]:
                    favs.append((category, subcategory))
        return favs

    def rename_command(self, category: str, old_name: str, new_name: str) -> None:
        categories = getattr(self.cfg, "Categories", {})

        if category not in categories:
            return

        commands = categories[category]

        if old_name not in commands:
            return

        if new_name in commands and new_name != old_name:
            if not messagebox.askokcancel(
                "Rename Command",
                f"'{new_name}' already exists in '{category}'.\n\nOverwrite it?"
            ):
                return

        commands[new_name] = commands.pop(old_name)

        favorites = getattr(self.cfg, "Favorites", [])
        if isinstance(favorites, list):
            for item in favorites:
                if (
                    isinstance(item, list)
                    and len(item) >= 2
                    and item[0] == category
                    and item[1] == old_name
                ):
                    item[1] = new_name

        recent = getattr(self.cfg, "Recent", [])
        if isinstance(recent, list):
            for item in recent:
                if (
                    isinstance(item, list)
                    and len(item) >= 2
                    and item[0] == category
                    and item[1] == old_name
                ):
                    item[1] = new_name

        usage = getattr(self.cfg, "Usage", {})
        if isinstance(usage, dict):
            old_key = f"{category}/{old_name}"
            new_key = f"{category}/{new_name}"
            if old_key in usage:
                usage[new_key] = usage.pop(old_key)

        self.persist_full_config()
        self.rebuild_category_buttons()
        self.rebuild_favorites_bar()

    def get_windows_dict(self) -> dict:
        windows = getattr(self.cfg, "Windows", None)
        if windows is None or not isinstance(windows, dict):
            windows = {}
            setattr(self.cfg, "Windows", windows)
        return windows

    def persist_windows(self) -> None:
        windows = self.get_windows_dict()
        try:
            text = CONFIG_FILE.read_text(encoding="utf-8")
            rendered = pprint.pformat(windows, indent=4)
            if re.search(r"(?m)^Windows\s*=", text):
                text = re.sub(
                    r"(?ms)^Windows\s*=\s*{.*?}(?=^\S|\Z)",
                    f"Windows = {rendered}\n",
                    text,
                )
            else:
                text += f"\n\nWindows = {rendered}\n"
            CONFIG_FILE.write_text(text, encoding="utf-8")
        except Exception as exc:
            self.log(f"Could not persist window profiles: {exc}")


    def get_hotkeys_dict(self) -> dict:
        hotkeys = getattr(self.cfg, "Hotkeys", None)
        if hotkeys is None or not isinstance(hotkeys, dict):
            hotkeys = {}
            setattr(self.cfg, "Hotkeys", hotkeys)
        return hotkeys


    def persist_hotkeys(self) -> None:
        hotkeys = self.get_hotkeys_dict()
        try:
            text = CONFIG_FILE.read_text(encoding="utf-8")
            rendered = pprint.pformat(hotkeys, indent=4)
            if re.search(r"(?m)^Hotkeys\s*=", text):
                text = re.sub(
                    r"(?ms)^Hotkeys\s*=\s*{.*?}(?=^\S|\Z)",
                    f"Hotkeys = {rendered}\n",
                    text,
                )
            else:
                text += f"\n\nHotkeys = {rendered}\n"
            CONFIG_FILE.write_text(text, encoding="utf-8")
        except Exception as exc:
            self.log(f"Could not persist hotkeys: {exc}")

    def open_hotkey_editor(self) -> None:
        HotkeyEditorWindow(self)


    def persist_hotkeys(self) -> None:
        hotkeys = self.get_hotkeys_dict()
        try:
            text = CONFIG_FILE.read_text(encoding="utf-8")
            rendered = pprint.pformat(hotkeys, indent=4)
            if re.search(r"(?m)^Hotkeys\s*=", text):
                text = re.sub(
                    r"(?ms)^Hotkeys\s*=\s*{.*?}(?=^\S|\Z)",
                    f"Hotkeys = {rendered}\n",
                    text,
                )
            else:
                text += f"\n\nHotkeys = {rendered}\n"
            CONFIG_FILE.write_text(text, encoding="utf-8")
        except Exception as exc:
            self.log(f"Could not persist hotkeys: {exc}")

    def get_disabled_plugins(self) -> list[str]:
        disabled = getattr(self.cfg, "DisabledPlugins", None)
        if disabled is None or not isinstance(disabled, list):
            disabled = []
            setattr(self.cfg, "DisabledPlugins", disabled)
        return disabled

    def persist_disabled_plugins(self) -> None:
        disabled = sorted(set(str(x) for x in self.get_disabled_plugins()))
        setattr(self.cfg, "DisabledPlugins", disabled)
        try:
            text = CONFIG_FILE.read_text(encoding="utf-8")
            rendered = pprint.pformat(disabled, indent=4)
            if re.search(r"(?m)^DisabledPlugins\s*=", text):
                text = re.sub(
                    r"(?ms)^DisabledPlugins\s*=\s*\[.*?\](?=^\S|\Z)",
                    f"DisabledPlugins = {rendered}\n",
                    text,
                )
            else:
                text += f"\n\nDisabledPlugins = {rendered}\n"
            CONFIG_FILE.write_text(text, encoding="utf-8")
        except Exception as exc:
            self.log(f"Could not persist disabled plugins: {exc}")

    def disable_plugin(self, name: str) -> None:
        disabled = self.get_disabled_plugins()
        if name not in disabled:
            disabled.append(name)
            self.persist_disabled_plugins()
        self.load_plugins(force=True)

    def enable_plugin(self, name: str) -> None:
        disabled = self.get_disabled_plugins()
        if name in disabled:
            disabled.remove(name)
            self.persist_disabled_plugins()
        self.load_plugins(force=True)

    def open_hotkey_editor(self) -> None:
        HotkeyEditorWindow(self)

    def open_plugin_manager(self) -> None:
        PluginManagerWindow(self)

    def _normalize_hotkey_target(self, target):
        if isinstance(target, (list, tuple)) and len(target) >= 2:
            return str(target[0]), str(target[1])
        if isinstance(target, dict):
            category = target.get("category")
            command = target.get("command")
            if category and command:
                return str(category), str(command)
        raise TermForgeError(
            "Hotkey target must be ['Category', 'Command'] or "
            "{'category': '...', 'command': '...'}."
        )

    def get_valid_hotkeys(self) -> dict[str, tuple[str, str]]:
        valid: dict[str, tuple[str, str]] = {}
        for hotkey, target in self.get_hotkeys_dict().items():
            try:
                category, command = self._normalize_hotkey_target(target)
                if category in getattr(self.cfg, "Categories", {}) and command in self.cfg.Categories[category]:
                    valid[str(hotkey)] = (category, command)
                else:
                    self.log(f"Skipping hotkey {hotkey!r}: target {target!r} not found in Categories.")
            except Exception as exc:
                self.log(f"Skipping hotkey {hotkey!r}: {exc}")
        return valid

    def trigger_hotkey_target(self, category: str, command: str, hotkey: str) -> None:
        self.set_status(f"Hotkey {hotkey} -> {category}/{command}")
        self.add_history_entry("hotkey", f"{hotkey} => {category}/{command}", source="hotkey")
        self.select_cmd(None, category, command)

    def initialize_hotkeys(self) -> None:
        hotkeys = self.get_valid_hotkeys()
        if not hotkeys:
            self.hotkeys_enabled = False
            self.hotkey_status = "No hotkeys configured."
            self.log(self.hotkey_status)
            return

        if pynput_keyboard is None:
            self.hotkeys_enabled = False
            self.hotkey_status = (
                "Global hotkeys unavailable: install pynput "
                "with 'python -m pip install pynput'."
            )
            self.log(self.hotkey_status)
            return

        if self.hotkey_listener is not None:
            try:
                self.hotkey_listener.stop()
            except Exception:
                pass
            self.hotkey_listener = None

        def make_handler(category: str, command: str, hotkey: str):
            def _handler():
                self.root.after(0, lambda: self.trigger_hotkey_target(category, command, hotkey))
            return _handler

        mapping = {
            hotkey: make_handler(category, command, hotkey)
            for hotkey, (category, command) in hotkeys.items()
        }

        try:
            self.hotkey_listener = pynput_keyboard.GlobalHotKeys(mapping)
            self.hotkey_listener.start()
            self.hotkeys_enabled = True
            self.hotkey_status = f"Global hotkeys active: {len(mapping)}"
            self.log(self.hotkey_status)
        except Exception as exc:
            self.hotkeys_enabled = False
            self.hotkey_status = f"Could not start global hotkeys: {exc}"
            self.log(self.hotkey_status)

    def show_hotkeys_help(self) -> None:
        hotkeys = self.get_valid_hotkeys()
        lines = [
            "Global Hotkeys",
            "",
            self.hotkey_status,
            "",
            "Config format:",
            "Hotkeys = {",
            "    '<ctrl>+<alt>+d': ['Admin_CMDs', 'Deploy'],",
            "}",
            "",
        ]
        if hotkeys:
            lines.append("Active mappings:")
            for hotkey, (category, command) in sorted(hotkeys.items()):
                lines.append(f"  {hotkey} -> {category} / {command}")
        else:
            lines.append("No valid hotkeys are currently configured.")
        messagebox.showinfo("Hotkeys", "\n".join(lines))

    def _read_plugin_metadata(self, module, file: Path) -> dict:
        api_version = getattr(module, "TERMFORGE_PLUGIN_API_VERSION", PLUGIN_API_VERSION)
        display_name = getattr(module, "PLUGIN_NAME", file.stem)
        plugin_version = getattr(module, "PLUGIN_VERSION", "0.1.0")
        description = getattr(module, "__doc__", "") or getattr(module, "PLUGIN_DESCRIPTION", "")
        has_run = callable(getattr(module, "run", None))
        compatible = api_version == PLUGIN_API_VERSION
        return {
            "name": file.stem,
            "display_name": display_name,
            "plugin_version": str(plugin_version),
            "api_version": api_version,
            "compatible": compatible,
            "description": description.strip(),
            "path": str(file),
            "has_run": has_run,
        }

    def load_plugins(self, force: bool = False) -> dict[str, object]:
        plugins: dict[str, object] = {}
        mtimes: dict[str, float] = {}
        errors: dict[str, str] = {}
        disabled_plugins = set(self.get_disabled_plugins())
        for file in sorted(PLUGIN_DIR.glob("*.py")):
            name = file.stem
            if name in disabled_plugins:
                errors[name] = "Disabled by user."
                continue
            try:
                mtime = file.stat().st_mtime
            except OSError as exc:
                errors[name] = f"Could not stat plugin: {exc}"
                continue
            if not force and name in self.plugins and self.plugin_mtimes.get(name) == mtime:
                plugins[name] = self.plugins[name]
                mtimes[name] = mtime
                continue
            try:
                spec = importlib.util.spec_from_file_location(f"termforge_plugin_{name}", file)
                if spec is None or spec.loader is None:
                    raise TermForgeError("Could not create plugin spec.")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                metadata = self._read_plugin_metadata(module, file)
                setattr(module, "__termforge_metadata__", metadata)
                if not metadata["compatible"]:
                    raise TermForgeError(
                        f"Unsupported plugin API version {metadata['api_version']}. "
                        f"This TermForge build supports API {PLUGIN_API_VERSION}."
                    )
                if not metadata["has_run"]:
                    raise TermForgeError("Plugin does not define run(app, context).")
                plugins[name] = module
                mtimes[name] = mtime
            except Exception as exc:
                errors[name] = str(exc)
        self.plugins = plugins
        self.plugin_mtimes = mtimes
        self.plugin_errors = errors
        self.log(f"Plugins loaded: {len(self.plugins)} ok, {len(self.plugin_errors)} errors")
        return self.plugins

    def reload_plugins_with_notice(self) -> None:
        self.load_plugins(force=False)
        self.set_status("Plugins reloaded.")
        messagebox.showinfo(
            "Plugins",
            f"Loaded: {len(self.plugins)}\nErrors: {len(self.plugin_errors)}",
        )

    def open_plugin_folder(self) -> None:
        try:
            if sys.platform.startswith("linux"):
                subprocess.Popen(["xdg-open", str(PLUGIN_DIR)])
            else:
                raise TermForgeError("Opening the plugin folder is only implemented for Linux.")
        except Exception as exc:
            self.show_error("Plugin Folder", str(exc))

    def run_plugin(self, cmd) -> None:
        self.load_plugins(force=False)
        if isinstance(cmd, str):
            plugin_name = cmd
            plugin_args = {}
        elif isinstance(cmd, dict):
            plugin_name = cmd.get("plugin") or cmd.get("name")
            plugin_args = dict(cmd)
        else:
            raise TermForgeError("Plugin command must be a plugin name or dict.")

        if not plugin_name:
            raise TermForgeError("Plugin command did not specify a plugin name.")

        plugin = self.plugins.get(plugin_name)
        if plugin is None:
            load_error = self.plugin_errors.get(plugin_name)
            if load_error:
                raise TermForgeError(f"Plugin '{plugin_name}' failed to load: {load_error}")
            raise TermForgeError(f"Plugin '{plugin_name}' was not found in {PLUGIN_DIR}.")

        run_fn = getattr(plugin, "run", None)
        if not callable(run_fn):
            raise TermForgeError(f"Plugin '{plugin_name}' does not define run(app, context).")

        context = {
            "window_id": self.window_id,
            "config": self.cfg,
            "plugin_dir": PLUGIN_DIR,
            "args": plugin_args.get("args", plugin_args),
            "app_version": APP_VERSION,
            "plugin_api_version": PLUGIN_API_VERSION,
        }
        self.set_status(f"Running plugin: {plugin_name}")
        self.add_history_entry("plugin", plugin_name, source="plugin")
        run_fn(self, context)

    def _run_helper(self, payload: dict) -> dict:
        command = [sys.executable, "-m", "termforge.xdo_helper"]
        self.log(f"Running helper action={payload.get('action')} payload={payload}")
        try:
            proc = subprocess.run(
                command,
                input=json.dumps(payload),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=HELPER_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise TermForgeError("Helper timed out.") from exc
        except Exception as exc:
            raise TermForgeError(f"Could not start helper: {exc}") from exc

        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        if stderr:
            logging.warning("helper stderr: %s", stderr)

        if proc.returncode != 0 and not stdout:
            raise TermForgeError(f"Helper exited with code {proc.returncode}" + (f": {stderr}" if stderr else ""))

        if not stdout:
            raise TermForgeError("Helper returned no data.")

        try:
            result = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise TermForgeError(f"Helper returned invalid JSON: {stdout!r}") from exc

        if result.get("status") != "ok":
            raise TermForgeError(result.get("error", "Helper reported an unknown error."))
        return result

    def validate_window_id(self, window_id) -> bool:
        if window_id in (None, "", "None"):
            return False
        try:
            result = self._run_helper({"action": "validate_window", "window_id": window_id})
            return bool(result.get("valid"))
        except Exception:
            return False

    def reuse_last_window(self) -> bool:
        if self.last_window_id is None:
            self.set_status("No remembered window.")
            return False
        if self.validate_window_id(self.last_window_id):
            self.window_id = self.last_window_id
            self.set_status(f"Reusing remembered window: {self.window_id}")
            return True
        self.set_status("Remembered window is no longer valid.")
        return False

    def safe_initial_select(self) -> None:
        try:
            if self.reuse_last_window():
                return
            self.select_target_window()
        except Exception as exc:
            self.log(f"Initial selection skipped: {exc}")

    def forget_saved_window(self) -> None:
        self.window_id = None
        self.last_window_id = None
        self.save_state()
        self.set_status("Forgot remembered window.")

    def select_target_window(self) -> None:
        self.root.withdraw()
        try:
            result = self._run_helper({"action": "select_window"})
        finally:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()

        selected = result.get("window_id")
        if not selected:
            raise TermForgeError("No window selected.")

        self.remember_window(selected)
        self.set_status(f"Selected window: {self.window_id}")

    def select_target_window_with_notice(self) -> None:
        try:
            self.select_target_window()
            messagebox.showinfo("Target Window", f"Selected window id: {self.window_id}")
        except Exception as exc:
            self.show_error("Target Window", str(exc))

    def select_profile(self, name: str) -> None:
        windows = self.get_windows_dict()
        saved = windows.get(name)

        if saved and self.validate_window_id(saved):
            self.window_id = saved
            self.set_status(f"Using profile '{name}' -> {saved}")
            return

        self.set_status(f"Select window for profile '{name}'")
        self.select_target_window()
        windows[name] = self.window_id
        self.persist_windows()

    def resolve_command_placeholders(self, cmd: str, shared_vars: dict[str, str] | None = None):
        if not isinstance(cmd, str):
            return cmd

        shared_vars = shared_vars or {}
        prompt_fields: list[str] = []
        seen: set[str] = set()

        for field_name in PLACEHOLDER_RE.findall(cmd):
            if field_name in shared_vars:
                continue
            if field_name not in seen:
                seen.add(field_name)
                prompt_fields.append(field_name)

        values = dict(shared_vars)

        if prompt_fields:
            prompt = MultiFieldPrompt(
                self.root,
                "Command Input",
                prompt_fields,
                heading="Enter command values",
            )
            entered = prompt.show()
            if entered is None:
                self.set_status("Command cancelled.")
                return None
            values.update(entered)

        resolved = cmd
        for field_name in PLACEHOLDER_RE.findall(cmd):
            resolved = resolved.replace(f"<{field_name}>", values.get(field_name, ""))
        return resolved

    def collect_chain_vars(self, steps) -> list[str]:
        names = []

        def add_name(name):
            name = str(name).strip()
            if name and name not in names:
                names.append(name)

        for step in steps:
            if not isinstance(step, (list, tuple)) or not step:
                continue

            # Explicit vars step: ["vars", ["path", "host"]]
            if step[0] == "vars" and len(step) > 1 and isinstance(step[1], (list, tuple)):
                for name in step[1]:
                    add_name(name)

            # Command placeholders: [2, "cd <path> && ssh <host>"]
            try:
                _cmd_type, cmd, _options = parse_command_entry(step)
            except Exception:
                continue

            if isinstance(cmd, str):
                for name in re.findall(r"<([^<>]+)>", cmd):
                    add_name(name)

        return names


    def substitute_chain_vars(self, text: str, values: dict[str, str]) -> str:
        for key, value in values.items():
            text = text.replace(f"<{key}>", value)
        return text


    def substitute_step_vars(self, step, values: dict[str, str]):
        if not isinstance(step, (list, tuple)):
            return step

        step = list(step)

        if len(step) > 1 and isinstance(step[1], str):
            step[1] = self.substitute_chain_vars(step[1], values)

        return step

    def resolve_shared_vars(self, names: list[str]) -> dict[str, str] | None:
        prompt = MultiFieldPrompt(
            self.root,
            "Shared Variables",
            names,
            heading="Enter shared variable values",
        )
        values = prompt.show()
        if values is None:
            self.set_status("Chain cancelled.")
            return None
        return values

    def confirm_command(self, cmd_type, cmd, options):
        if not options.get("confirm", False):
            return True
        msg = f"About to run:\n\n{cmd}\n\nType: {cmd_type}"
        if cmd_type in (2, "command", "send"):
            msg += f"\nTarget window: {self.window_id}"
        return messagebox.askokcancel("Confirm Command", msg)

    def send_to_selected_window(self, cmd: str, record_history: bool = True) -> None:
        if not self.window_id:
            raise TermForgeError("No target window selected.")

        self.set_status(f"Sending to window {self.window_id}: {cmd}")
        try:
            result = self._run_helper(
                {
                    "action": "send",
                    "window_id": self.window_id,
                    "text": cmd,
                    "key": "Return",
                    "focus_delay_ms": 150,
                }
            )
        except TermForgeError as exc:
            logging.warning("Send failed for window %s: %s", self.window_id, exc)
            self.window_id = None
            raise TermForgeError(
                "Could not send command to the selected window. "
                "The target may have closed, activation may have failed, or the X11 helper failed. "
                "Re-select the window and try again."
            ) from exc

        active_window = result.get("active_window")
        self.remember_window(self.window_id)
        if record_history:
            self.add_history_entry(2, cmd, source="send")
        self.set_status(f"Sent to selected window {self.window_id} (active {active_window}).")

    def send_text_to_window(self, text: str) -> None:
        self.send_to_selected_window(text)

    def spawn_terminal(self, cmd: str, record_history: bool = True) -> None:
        if record_history:
            self.add_history_entry(1, cmd, source="spawn")
        self.set_status(f"Spawning new terminal command: {cmd}")
        subprocess.Popen([self.application, "--", "bash", "-lc", cmd])

    def run_detached(self, cmd: str, record_history: bool = True) -> None:
        if record_history:
            self.add_history_entry(3, cmd, source="detached")
        self.set_status(f"Running detached command: {cmd}")
        subprocess.Popen(cmd, shell=True)

    def run_sleep(self, seconds) -> None:
        self.set_status(f"Sleeping {seconds}s...")
        time.sleep(float(seconds))

    def run_chain(self, steps, source="chain") -> None:
        if not isinstance(steps, (list, tuple)) or not steps:
            raise TermForgeError("Chain command requires a non-empty list of steps.")

        total = len(steps)
        shared_vars: dict[str, str] = {}

        # Collect all declared vars once before execution.
        var_names = self.collect_chain_vars(steps)
        if var_names:
            values = self.resolve_shared_vars(var_names)
            if values is None:
                self.set_status("Chain cancelled during shared vars.")
                return
            shared_vars.update(values)

        runner = ChainRunnerWindow(self.root, total)

        for index, step in enumerate(steps, start=1):
            if not isinstance(step, (list, tuple)) or not step:
                runner.step_failed(f"Invalid chain step: {step!r}")
                raise TermForgeError(f"Invalid chain step: {step!r}")

            step_kind = step[0]

            try:
                if step_kind == "vars":
                    runner.step_running(index, total, "shared vars")
                    if len(step) < 2 or not isinstance(step[1], (list, tuple)):
                        raise TermForgeError("vars step requires a list of variable names.")
                    names = [str(name) for name in step[1]]
                    runner.step_done(f"Shared vars already captured: {', '.join(names)}")
                    continue

                if step_kind == "sleep":
                    if len(step) < 2:
                        raise TermForgeError("Sleep step requires a number of seconds.")
                    runner.step_running(index, total, f"sleep {step[1]}")
                    self.run_sleep(step[1])
                    runner.step_done(f"Slept {step[1]}s")
                    continue

                if step_kind == "select_profile":
                    if len(step) < 2:
                        raise TermForgeError("select_profile step requires a profile name.")
                    runner.step_running(index, total, f"select profile {step[1]}")
                    self.select_profile(str(step[1]))
                    runner.step_done(f"Using profile {step[1]}")
                    continue

                step_type, step_cmd, step_options = parse_command_entry(step)

                if isinstance(step_cmd, str):
                    step_cmd = self.resolve_command_placeholders(
                        step_cmd,
                        shared_vars=shared_vars,
                    )
                    if step_cmd is None:
                        runner.step_failed("Chain cancelled.")
                        return

                runner.step_running(index, total, str(step_cmd))

                self.run_cmd(
                    step_type,
                    step_cmd,
                    step_options,
                    None,
                    record_history=False,
                    shared_vars=shared_vars,
                )

                runner.step_done(str(step_cmd))

            except Exception as exc:
                runner.step_failed(str(exc))
                raise

        self.add_history_entry("chain", f"{total} steps", source=source)
        self.set_status(f"Chain complete: {total} step(s).")
        runner.finished()

    def duplicate_command(self, category: str, name: str) -> None:
        categories = getattr(self.cfg, "Categories", {})

        if category not in categories:
            return

        commands = categories[category]

        if name not in commands:
            return

        original = copy.deepcopy(commands[name])

        # strip prior Copy suffix if duplicating a copy
        base_name = re.sub(r' Copy(?: \d+)?$', '', name)

        base = f"{base_name} Copy"
        new_name = base
        counter = 2

        while new_name in commands:
            new_name = f"{base} {counter}"
            counter += 1

        commands[new_name] = original

        self.persist_categories()
        self.rebuild_category_buttons()

    def delete_command(self, category: str, name: str) -> None:
        categories = getattr(self.cfg, "Categories", {})

        if category not in categories:
            return

        commands = categories[category]

        if name not in commands:
            return

        del commands[name]

        # clean related metadata
        self.remove_favorite(category, name)

        recent = getattr(self.cfg, "Recent", [])
        if isinstance(recent, list):
            self.cfg.Recent = [
                item for item in recent
                if not (
                    isinstance(item, (list, tuple))
                    and len(item) >= 2
                    and item[0] == category
                    and item[1] == name
                )
            ]

        usage = getattr(self.cfg, "Usage", {})
        if isinstance(usage, dict):
            usage.pop(f"{category}/{name}", None)

        self.persist_full_config()
        self.rebuild_category_buttons()
        self.rebuild_favorites_bar()

    def run_cmd(
        self,
        cmd_type,
        cmd,
        options=None,
        current_window=None,
        record_history: bool = True,
        shared_vars: dict[str, str] | None = None,
    ) -> None:
        try:
            if options is None:
                options = {}
            normalized = cmd_type
            if isinstance(cmd_type, str):
                normalized = cmd_type.strip().lower()

            if normalized == "chain":
                self.run_chain(cmd, source="chain")
                return

            resolved_cmd = cmd
            if normalized in (1, 2, 3, "spawn", "command", "send", "detached") and isinstance(cmd, str):
                resolved_cmd = self.resolve_command_placeholders(cmd, shared_vars=shared_vars)
                if resolved_cmd is None:
                    return

            if not self.confirm_command(normalized, resolved_cmd, options):
                self.set_status("Command cancelled by user.")
                return

            if normalized in (0, "select"):
                self.select_target_window()
            elif normalized in (1, "spawn"):
                self.spawn_terminal(str(resolved_cmd), record_history=record_history)
            elif normalized in (2, "command", "send"):
                self.send_to_selected_window(str(resolved_cmd), record_history=record_history)
            elif normalized in (3, "detached"):
                self.run_detached(str(resolved_cmd), record_history=record_history)
            elif normalized == "plugin":
                self.run_plugin(cmd)
            else:
                raise TermForgeError(f"Unknown command type: {cmd_type}")
        except Exception as exc:
            self.show_error("Command failed", f"{exc}\n\n{traceback.format_exc()}")

    def select_cmd(self, parent_window, category: str, subcategory: str) -> None:
        entry = self.cfg.Categories[category][subcategory]
        cmd_type, cmd, options = parse_command_entry(entry)

        self.add_recent(category, subcategory)
        self.add_usage(category, subcategory)

        self.run_cmd(cmd_type, cmd, options, parent_window)

    def run_favorite(self, category: str, subcategory: str) -> None:
        self.select_cmd(None, category, subcategory)

    def category_matches_search(self, category: str, query: str) -> bool:
        if not query:
            return True
        q = query.lower().strip()
        if q in category.lower():
            return True
        for subcategory, entry in self.cfg.Categories.get(category, {}).items():
            if q in subcategory.lower():
                return True
            try:
                _cmd_type, cmd, _options = parse_command_entry(entry)
            except Exception:
                continue
            if isinstance(cmd, str) and q in cmd.lower():
                return True
            if isinstance(cmd, (list, tuple)) and q in json.dumps(cmd).lower():
                return True
        return False

    def update_category_filter(self, *_args) -> None:
        query = self.search_var.get().strip()
        visible = 0
        for category, button in self.category_buttons.items():
            if self.category_matches_search(category, query):
                if not button.winfo_ismapped():
                    button.pack(pady=2)
                visible += 1
            else:
                if button.winfo_ismapped():
                    button.pack_forget()
        if query:
            self.set_status(f"Search: showing {visible} matching categories.")
        else:
            self.status_var.set("Ready.")

    def collect_search_results(self, query: str) -> list[tuple[str, str]]:
        results = []
        q = query.lower().strip()
        if not q:
            return results
        for category, commands in self.cfg.Categories.items():
            for subcategory, entry in commands.items():
                text_parts = [category, subcategory]
                try:
                    _cmd_type, cmd, _options = parse_command_entry(entry)
                    text_parts.append(json.dumps(cmd) if not isinstance(cmd, str) else cmd)
                except Exception:
                    pass
                if q in " ".join(text_parts).lower():
                    results.append((category, subcategory))
        return results

    def open_search_results(self, *_args) -> None:
        query = self.search_var.get().strip()
        if not query:
            self.set_status("Enter a search term first.")
            return

        results = self.collect_search_results(query)
        win = Toplevel(self.root)
        win.title(f"Search Results: {query}")
        win.protocol("WM_DELETE_WINDOW", win.destroy)

        Label(
            win,
            text=f"Matches for: {query}",
            bd=4,
            width=40,
            bg="lightgreen",
            fg="black",
            relief="raised",
        ).pack(padx=8, pady=(8, 6))

        if not results:
            Label(win, text="No matching commands found.").pack(padx=8, pady=8)
        else:
            for category, subcategory in results:
                Button(
                    win,
                    text=f"{category} → {subcategory}",
                    width=40,
                    bg="black",
                    fg="yellow",
                    command=lambda c=category, s=subcategory, w=win: self.select_cmd(w, c, s),
                ).pack(pady=2, padx=8)

        Button(win, text="Close", width=40, bg="red", fg="black", command=win.destroy).pack(pady=(8, 8))

    def clear_search(self) -> None:
        self.search_var.set("")
        self.update_category_filter()

    def open_history_window(self) -> None:
        win = Toplevel(self.root)
        win.title("Command History")
        win.geometry("900x420")
        win.protocol("WM_DELETE_WINDOW", win.destroy)

        outer = Frame(win, padx=8, pady=8)
        outer.pack(fill=BOTH, expand=True)
        Label(outer, text="Recent Commands", bd=4, width=40, bg="lightgreen", fg="black", relief="raised").pack(pady=(0, 8))

        body = Frame(outer)
        body.pack(fill=BOTH, expand=True)
        left = Frame(body)
        left.pack(side=LEFT, fill=Y)
        right = Frame(body)
        right.pack(side=RIGHT, fill=BOTH, expand=True, padx=(8, 0))

        listbox = Listbox(left, width=44, height=18)
        listbox.pack(side=LEFT, fill=Y)
        scrollbar = Scrollbar(left, command=listbox.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        listbox.config(yscrollcommand=scrollbar.set)

        info = Text(right, wrap="word", width=72, height=20)
        info.pack(fill=BOTH, expand=True)
        selected_entry = {"value": None}

    def get_usage(self) -> dict:
        usage = getattr(self.cfg, "Usage", {})
        if not isinstance(usage, dict):
            usage = {}
            setattr(self.cfg, "Usage", usage)
        return usage


    def add_usage(self, category: str, command: str) -> None:
        usage = self.get_usage()
        key = f"{category}/{command}"
        usage[key] = int(usage.get(key, 0)) + 1
        self.persist_full_config()


    def parse_command_entry_public(self, entry):
        return parse_command_entry(entry)

    def persist_categories(self) -> None:
        categories = getattr(self.cfg, "Categories", {})
        try:
            text = CONFIG_FILE.read_text(encoding="utf-8")
            rendered = pprint.pformat(categories, indent=4)
            if re.search(r"(?m)^Categories\s*=", text):
                text = re.sub(
                    r"(?ms)^Categories\s*=\s*{.*?}(?=^\S|\Z)",
                    f"Categories = {rendered}\n",
                    text,
                )
            else:
                text += f"\n\nCategories = {rendered}\n"
            CONFIG_FILE.write_text(text, encoding="utf-8")
        except Exception as exc:
            self.log(f"Could not persist categories: {exc}")

    def export_config_backup(self) -> None:
        try:
            if not CONFIG_FILE.exists():
                messagebox.showerror("Export Config", "Config file does not exist yet.")
                return

            target = filedialog.asksaveasfilename(
                title="Export TermForge Config Backup",
                defaultextension=".py",
                initialfile="termforge_config_backup.py",
                filetypes=[
                    ("Python config", "*.py"),
                    ("All files", "*.*"),
                ],
            )

            if not target:
                return

            shutil.copy2(CONFIG_FILE, target)
            self.set_status(f"Exported config backup to {target}")
            messagebox.showinfo("Export Config", f"Config exported to:\n\n{target}")

        except Exception as exc:
            messagebox.showerror("Export Config", str(exc))


    def import_config_backup(self) -> None:
        try:
            source = filedialog.askopenfilename(
                title="Import TermForge Config Backup",
                filetypes=[
                    ("Python config", "*.py"),
                    ("All files", "*.*"),
                ],
            )

            if not source:
                return

            if not messagebox.askokcancel(
                "Import Config",
                "Importing a backup will replace your current TermForge config.\n\nContinue?"
            ):
                return

            # Validate before replacing current config.
            spec = importlib.util.spec_from_file_location("termforge_import_test", source)
            if spec is None or spec.loader is None:
                messagebox.showerror("Import Config", "Could not read selected config file.")
                return

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            if not hasattr(module, "Categories"):
                messagebox.showerror("Import Config", "Selected file does not contain Categories.")
                return

            backup_current = CONFIG_FILE.with_suffix(".py.before_import")
            if CONFIG_FILE.exists():
                shutil.copy2(CONFIG_FILE, backup_current)

            shutil.copy2(source, CONFIG_FILE)

            self.cfg = load_config()
            self.rebuild_category_buttons()
            self.rebuild_favorites_bar()
            self.initialize_hotkeys()
            self.load_plugins(force=True)

            self.set_status("Imported config backup.")
            messagebox.showinfo(
                "Import Config",
                f"Config imported successfully.\n\nPrevious config backup:\n{backup_current}"
            )

        except Exception as exc:
            messagebox.showerror("Import Config", str(exc))

    def reload_from_config_with_notice(self, silent: bool = False) -> None:
        try:
            self.cfg = load_config()
            self.initialize_hotkeys()
            self.load_plugins(force=True)
            for child in list(self.root.winfo_children()):
                child.destroy()
            self.category_buttons = {}
            self.build_main()
            if not silent:
                messagebox.showinfo("Reloaded", "Config reloaded.")
        except Exception as exc:
            if not silent:
                messagebox.showerror("Reload failed", str(exc))
            else:
                self.log(f"Silent reload failed: {exc}")

    def open_command_editor(self) -> None:
        CommandEditorWindow(self)


    def open_category_editor(self) -> None:
        CategoryEditorWindow(self)


    def open_command_palette(self, event=None) -> None:
        CommandPaletteWindow(self)
        return "break"



    def bind_global_shortcuts(self) -> None:
        self.root.bind_all("<Control-p>", self.open_command_palette)
        self.root.bind_all("<Control-P>", self.open_command_palette)


    def persist_full_config(self) -> None:
        try:
            terminal = getattr(self.cfg, "terminal", {"application": "gnome-terminal"})
            debug = getattr(self.cfg, "debug", {"Flag": False})
            windows = getattr(self.cfg, "Windows", {})
            favorites = getattr(self.cfg, "Favorites", [])
            recent = getattr(self.cfg, "Recent", [])
            usage = getattr(self.cfg, "Usage", {})
            hotkeys = getattr(self.cfg, "Hotkeys", {})
            disabled_plugins = getattr(self.cfg, "DisabledPlugins", [])
            categories = getattr(self.cfg, "Categories", {})
            chain_templates = getattr(self.cfg, "ChainTemplates", {})

            lines = [
                "# TermForge user configuration",
                "# Edit Categories below.",
                "",
                f"terminal = {pprint.pformat(terminal, indent=4)}",
                f"debug = {pprint.pformat(debug, indent=4)}",
                f"Windows = {pprint.pformat(windows, indent=4)}",
                f"Recent = {pprint.pformat(recent, indent=4)}",
                f"Usage = {pprint.pformat(usage, indent=4)}",
                f"Hotkeys = {pprint.pformat(hotkeys, indent=4)}",
                f"DisabledPlugins = {pprint.pformat(disabled_plugins, indent=4)}",
                f"ChainTemplates = {pprint.pformat(chain_templates, indent=4)}",
                f"Categories = {pprint.pformat(categories, indent=4)}",
                "",
            ]

            CONFIG_FILE.write_text("\n".join(lines), encoding="utf-8")
        except Exception as exc:
            chain_templates = getattr(self.cfg, "ChainTemplates", {})

            lines = [
                "# TermForge user configuration",
                "# Edit Categories below.",
                "",
                f"terminal = {pprint.pformat(terminal, indent=4)}",
                f"debug = {pprint.pformat(debug, indent=4)}",
                f"Windows = {pprint.pformat(windows, indent=4)}",
                f"Recent = {pprint.pformat(recent, indent=4)}",
                f"Usage = {pprint.pformat(usage, indent=4)}",
                f"Hotkeys = {pprint.pformat(hotkeys, indent=4)}",
                f"DisabledPlugins = {pprint.pformat(disabled_plugins, indent=4)}",
                f"ChainTemplates = {pprint.pformat(chain_templates, indent=4)}",
                f"Categories = {pprint.pformat(categories, indent=4)}",
                "",
            ]

            CONFIG_FILE.write_text("\n".join(lines), encoding="utf-8")
        except Exception as exc:
            self.log(f"Could not persist full config: {exc}")

    def persist_categories(self) -> None:
        self.persist_full_config()

    def persist_hotkeys(self) -> None:
        self.persist_full_config()

    def persist_windows(self) -> None:
        self.persist_full_config()

    def get_recent(self) -> list[tuple[str, str]]:
        raw = getattr(self.cfg, "Recent", [])
        if not isinstance(raw, list):
            return []
        return [(c, s) for c, s in raw if isinstance(c, str) and isinstance(s, str)]

    def persist_recent(self) -> None:
        self.persist_full_config()

    def add_recent(self, category: str, command: str) -> None:
        recent = getattr(self.cfg, "Recent", None)
        if recent is None or not isinstance(recent, list):
            recent = []
            setattr(self.cfg, "Recent", recent)

        pair = [category, command]
        if pair in recent:
            recent.remove(pair)
        recent.insert(0, pair)
        del recent[20:]
        self.persist_recent()

    def persist_favorites(self) -> None:
        self.persist_full_config()

    def add_favorite(self, category: str, command: str) -> None:
        favorites = getattr(self.cfg, "Favorites", None)
        if favorites is None or not isinstance(favorites, list):
            favorites = []
            setattr(self.cfg, "Favorites", favorites)
        pair = [category, command]
        if pair not in favorites:
            favorites.append(pair)
            self.persist_favorites()

    def remove_favorite(self, category: str, command: str) -> None:
        favorites = getattr(self.cfg, "Favorites", None)
        if not isinstance(favorites, list):
            return
        pair = [category, command]
        if pair in favorites:
            favorites.remove(pair)
            self.persist_favorites()

    def run_favorite(self, category: str, subcategory: str) -> None:
        self.select_cmd(None, category, subcategory)

    def rebuild_favorites_bar(self) -> None:
        if not hasattr(self, "favorites_frame"):
            return

        for child in self.favorites_frame.winfo_children():
            child.destroy()

        favorites = self.get_favorites()
        for category, command in favorites:
            Button(
                self.favorites_frame,
                text=command,
                width=13,
                bg="#1f4e79",
                fg="white",
                command=lambda c=category, s=command: self.run_favorite(c, s),
            ).pack(side=LEFT, padx=2, pady=2)

    def rebuild_category_buttons(self) -> None:
        if not hasattr(self, "categories_frame"):
            return

        for child in self.categories_frame.winfo_children():
            child.destroy()

        self.category_buttons = {}
        categories = getattr(self.cfg, "Categories", {})
        for category in categories:
            btn = Button(
                self.categories_frame,
                text=category,
                width=28,
                bg="black",
                fg="yellow",
                command=lambda c=category: self.open_category(c),
            )
            btn.pack(pady=2)
            self.category_buttons[category] = btn

    def build_menu(self) -> None:
        menubar = Menu(self.root)

        file_menu = Menu(menubar, tearoff=0)
        file_menu.add_command(label="Export Config Backup", command=self.export_config_backup)
        file_menu.add_command(label="Import Config Backup", command=self.import_config_backup)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        tools_menu = Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Command Palette\tCtrl+P", command=self.open_command_palette)
        tools_menu.add_separator()
        tools_menu.add_command(label="Select Target Window", command=self.select_target_window_with_notice)
        tools_menu.add_command(label="Reuse Saved Window", command=self.reuse_last_window)
        tools_menu.add_command(label="Forget Saved Window", command=self.forget_saved_window)
        tools_menu.add_separator()
        tools_menu.add_command(label="History", command=self.open_history_window)
        tools_menu.add_separator()
        tools_menu.add_command(label="Category Editor", command=self.open_category_editor)
        tools_menu.add_command(label="Command / Chain Editor", command=self.open_command_editor)
        tools_menu.add_separator()
        tools_menu.add_command(label="Plugin Manager", command=self.open_plugin_manager)
        tools_menu.add_command(label="Reload Plugins", command=self.reload_plugins_with_notice)
        tools_menu.add_command(label="Open Plugin Folder", command=self.open_plugin_folder)
        tools_menu.add_separator()
        tools_menu.add_command(label="Hotkeys", command=self.show_hotkeys_help)
        tools_menu.add_command(label="Hotkey Editor", command=self.open_hotkey_editor)
        menubar.add_cascade(label="Tools", menu=tools_menu)

        help_menu = Menu(menubar, tearoff=0)
        help_menu.add_command(label="About TermForge", command=self.show_about)
        help_menu.add_command(label="Command Palette", command=self.open_command_palette)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)

    def show_about(self) -> None:
        messagebox.showinfo(
            "About TermForge",
            f"{APP_NAME} {APP_VERSION}\n\n"
            "Terminal workflow engine for X11 terminals.\n"
            "Build command chains, hotkeys, plugins, and reusable terminal automations.",
        )

    def build_main(self) -> None:
        self.build_menu()

        frame = Frame(self.root, padx=8, pady=8)
        frame.pack()
        self.categories_frame = Frame(frame)
        self.categories_frame.pack()
        self.category_buttons = {}

        Label(
            frame,
            text=f"{APP_NAME} {APP_VERSION}",
            bd=4,
            width=28,
            bg="lightgreen",
            fg="black",
            relief="raised",
        ).pack(pady=(0, 8))

        favorites = self.get_favorites()
        if favorites:
            Label(frame, text="Favorites", width=28, bg="#d9edf7", fg="black", relief="groove").pack(pady=(0, 4))
            self.favorites_frame = Frame(frame)
        categories = getattr(self.cfg, "Categories", {})
        for category in categories:
            btn = Button(
                self.categories_frame,
                text=category,
                width=28,
                bg="black",
                fg="yellow",
                command=lambda c=category: self.open_category(c),
            )
            btn.pack(pady=2)
            self.category_buttons[category] = btn

        Label(
            frame,
            text="Use the Tools menu for windows, history, plugins, hotkeys, and editors.",
            width=56,
            bg="#f7f7d0",
            fg="black",
            relief="groove",
            pady=4,
        ).pack(fill=X, pady=(8, 4))

        Label(
            frame,
            textvariable=self.status_var,
            anchor="w",
            justify="left",
            width=40,
            wraplength=420,
            bg="#f0f0f0",
            fg="black",
            relief="sunken",
            padx=6,
            pady=4,
        ).pack(fill=X, pady=(4, 0))

    def open_category(self, category: str) -> None:
        win = Toplevel(self.root)
        win.title(category)
        win.protocol("WM_DELETE_WINDOW", win.destroy)

        Label(
            win,
            text=category,
            bd=4,
            width=28,
            bg="lightgreen",
            fg="black",
            relief="raised",
        ).pack(padx=8, pady=(8, 6))

        for subcategory in self.cfg.Categories[category]:
            Button(
                win,
                text=subcategory,
                width=28,
                bg="black",
                fg="yellow",
                command=lambda c=category, s=subcategory, w=win: self.select_cmd(w, c, s),
            ).pack(pady=2, padx=8)

        Button(win, text="Close", width=28, bg="red", fg="black", command=win.destroy).pack(pady=(8, 8))


def main() -> int:
    ensure_user_config()
    cfg = load_config()
    root = Tk()
    TermForgeApp(root, cfg)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
