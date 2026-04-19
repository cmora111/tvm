from __future__ import annotations

import importlib.util
import json
import logging
import pprint
import re
import subprocess
import sys
import time
import traceback
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
    Text,
    Tk,
    Toplevel,
    messagebox,
    OptionMenu,
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
        "Hotkeys = {}",
        "DisabledPlugins = []",
        f"Categories = {repr(getattr(default_config, 'Categories', {}))}",
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
        self.window.geometry("760x360")
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

        Button(outer, text="Close", width=16, bg="red", fg="black", command=self.window.destroy).pack(pady=(8, 0))

    def log(self, marker: str, message: str) -> None:
        self.output.insert("end", f"{marker} {message}\n")
        self.output.see("end")
        self.output.update_idletasks()

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
        item = self.current_item()
        if not item:
            return
        if item["status"] != "loaded":
            messagebox.showerror("Plugin Manager", "Only loaded plugins can be run.")
            return
        try:
            self.app.run_plugin(item["name"])
        except Exception as exc:
            messagebox.showerror("Plugin Manager", str(exc))

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

    def __init__(self, parent, initial_steps=None):
        self.parent = parent
        self.result = None
        self.window = Toplevel(parent)
        self.window.title("Visual Chain Builder")
        self.window.geometry("980x640")
        self.window.transient(parent)
        self.window.grab_set()

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
        )
        help_box.config(state="disabled")

        btns = Frame(outer)
        btns.pack(fill=X, pady=(10, 0))
        Button(btns, text="Add / Update Step", width=16, bg="darkgreen", fg="white", command=self.add_or_update_step).pack(side=LEFT, padx=(0, 6))
        Button(btns, text="Duplicate Step", width=14, bg="#555555", fg="white", command=self.duplicate_step).pack(side=LEFT, padx=(0, 6))
        Button(btns, text="Delete Step", width=14, bg="#7f6000", fg="white", command=self.delete_step).pack(side=LEFT, padx=(0, 6))
        Button(btns, text="Move Up", width=12, bg="#444444", fg="white", command=self.move_up).pack(side=LEFT, padx=(0, 6))
        Button(btns, text="Move Down", width=12, bg="#444444", fg="white", command=self.move_down).pack(side=LEFT, padx=(0, 6))
        Button(btns, text="Load Selected", width=14, bg="#2f5597", fg="white", command=self.load_selected).pack(side=LEFT, padx=(0, 6))
        Button(btns, text="Apply to Editor", width=14, bg="navy", fg="white", command=self.apply_and_close).pack(side=LEFT, padx=(0, 6))
        Button(btns, text="Close", width=12, bg="red", fg="black", command=self.close).pack(side=RIGHT)

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
            self.hint_var.set("Plain text terminal command sent to selected window")
        elif kind == "spawn":
            self.value_label.config(text="Command:")
            self.hint_var.set("Plain text command run in a new terminal")
        elif kind == "detached":
            self.value_label.config(text="Command:")
            self.hint_var.set("Plain text detached command run in background")
        else:
            self.value_label.config(text="Value:")
            self.hint_var.set("")

    def step_to_label(self, step):
        if isinstance(step, (list, tuple)) and step:
            kind = step[0]
            return f"{kind}: {step!r}"
        return repr(step)

    def refresh(self):
        self.listbox.delete(0, END)
        for step in self.steps:
            self.listbox.insert(END, self.step_to_label(step))

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

        self.category_choices = []
        self.category_var = StringVar()

        self.category_menu = OptionMenu(form, self.category_var, "")
        self.category_menu.config(width=38)
        self.category_menu.grid(row=0, column=1, sticky="w", pady=3)

        Label(form, text="Command Name:", width=14, anchor="w").grid(row=1, column=0, sticky="w", pady=3)
        self.name_var = StringVar()
        Entry(form, textvariable=self.name_var, width=42).grid(row=1, column=1, sticky="ew", pady=3)

        Label(form, text="Type:", width=14, anchor="w").grid(row=2, column=0, sticky="w", pady=3)

        self.type_choices = {
            "Select Window": "0",
            "Spawn Terminal": "1",
            "Send To Window": "2",
            "Detached Command": "3",
            "Chain": "chain",
            "Plugin": "plugin",
        }

        self.type_var = StringVar(value="Send To Window")
        self.type_menu = OptionMenu(form, self.type_var, *self.type_choices.keys())
        self.type_menu.config(width=38)
        self.type_menu.grid(row=2, column=1, sticky="w", pady=3)

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

        self.snapshot = []
        self.listbox.bind("<<ListboxSelect>>", self.on_select)
        self.type_var.trace_add("write", self.update_type_ui)
        self.refresh_category_menu()
        self.refresh()
        self.clear_form()

    def update_type_ui(self, *_args):
        cmd_type_raw = self.type_choices.get(self.type_var.get(), "2").strip().lower()

        if cmd_type_raw == "chain":
            self.command_label.config(text="Chain JSON:")
            self.builder_button.config(state="normal")
            self.chain_hint.config(text="Build visually or edit JSON directly")
        elif cmd_type_raw == "plugin":
            self.command_label.config(text="Plugin Name:")
            self.builder_button.config(state="disabled")
            self.chain_hint.config(text="Enter the plugin name, e.g. hello_world")
        elif cmd_type_raw == "0":
            self.command_label.config(text="Command:")
            self.builder_button.config(state="disabled")
            self.chain_hint.config(text="Usually not needed; select window action")
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
            except Exception:
                initial = []
        builder = ChainBuilderWindow(self.window, initial_steps=initial)
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

    def refresh_category_menu(self):
        categories = getattr(self.app.cfg, "Categories", {})
        self.category_choices = sorted(categories.keys())

        menu = self.category_menu["menu"]
        menu.delete(0, "end")

        for name in self.category_choices:
            menu.add_command(
                label=name,
                command=lambda value=name: self.category_var.set(value)
            )

        current = self.category_var.get().strip()
        if self.category_choices:
            if current not in self.category_choices:
                self.category_var.set(self.category_choices[0])
        else:
            self.category_var.set("")

    def on_select(self, _event=None):
        idxs = self.listbox.curselection()
        if not idxs:
            return
        category, name, entry = self.snapshot[idxs[0]]
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

    def clear_form(self):
        if self.category_choices:
            self.category_var.set(self.category_choices[0])
        else:
            self.category_var.set("")
        self.name_var.set("")
        self.type_var.set("Send To Window")
        self.command_text.delete("1.0", END)
        self.options_text.delete("1.0", END)
        self.options_text.insert("1.0", "{}")
        self.update_type_ui()

    def _parse_form(self):
        category = self.category_var.get().strip()
        name = self.name_var.get().strip()
        cmd_type_raw = self.type_choices.get(self.type_var.get(), "2").strip()
        command_raw = self.command_text.get("1.0", END).strip()
        options_raw = self.options_text.get("1.0", END).strip() or "{}"

        if not category or not name or not cmd_type_raw:
            raise ValueError("Category, command name, and type are required.")

        if cmd_type_raw.lower() == "chain":
            cmd_type = "chain"
            command = json.loads(command_raw) if command_raw else []
            if not isinstance(command, list):
                raise ValueError("Chain JSON must decode to a list.")
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
            if self.window.winfo_exists() and self.listbox.winfo_exists():
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
        self.clear_form()

        try:
            if self.window.winfo_exists() and self.listbox.winfo_exists():
                self.refresh()
        except Exception:
            pass

class MoveCommandDialog:
    def __init__(self, parent, source_category: str, commands: list[str], categories: list[str]):
        self.result = None
        self.window = Toplevel(parent)
        self.window.title("Move Command")
        self.window.transient(parent)
        self.window.grab_set()
        self.window.resizable(False, False)
        self.window.protocol("WM_DELETE_WINDOW", self.cancel)

        outer = Frame(self.window, padx=10, pady=10)
        outer.pack(fill=BOTH, expand=True)

        Label(
            outer,
            text=f"Move command from '{source_category}'",
            bd=2,
            relief="groove",
            width=34,
            bg="lightgreen",
            fg="black",
        ).pack(pady=(0, 10))

        row1 = Frame(outer)
        row1.pack(fill=X, pady=3)
        Label(row1, text="Command:", width=14, anchor="w").pack(side=LEFT)
        self.command_var = StringVar(value=commands[0] if commands else "")
        OptionMenu(row1, self.command_var, *(commands if commands else [""])).pack(side=RIGHT, fill=X, expand=True)

        row2 = Frame(outer)
        row2.pack(fill=X, pady=3)
        Label(row2, text="Target Category:", width=14, anchor="w").pack(side=LEFT)
        target_choices = categories if categories else [""]
        self.target_var = StringVar(value=target_choices[0])
        OptionMenu(row2, self.target_var, *target_choices).pack(side=RIGHT, fill=X, expand=True)

        buttons = Frame(outer)
        buttons.pack(fill=X, pady=(12, 0))
        Button(buttons, text="OK", width=12, bg="darkgreen", fg="white", command=self.submit).pack(side=LEFT)
        Button(buttons, text="Cancel", width=12, bg="red", fg="black", command=self.cancel).pack(side=RIGHT)

    def submit(self):
        self.result = {
            "command_name": self.command_var.get().strip(),
            "target_category": self.target_var.get().strip(),
        }
        try:
            self.window.grab_release()
        except Exception:
            pass
        self.window.destroy()

    def cancel(self):
        self.result = None
        try:
            self.window.grab_release()
        except Exception:
            pass
        self.window.destroy()

    def show(self):
        self.window.wait_visibility()
        self.window.grab_set()
        self.window.wait_window(self.window)
        return self.result


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
        Button(action_row, text="Move Command", width=16, bg="#444444", fg="white", command=self.move_command).pack(side=LEFT, padx=(0, 6))
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
        idxs = self.listbox.curselection()
        if not idxs:
            return
        name, count = self.snapshot[idxs[0]]
        commands = self.get_categories().get(name, {})
        lines = [
            f"Category: {name}",
            f"Commands: {count}",
            "",
        ]
        if isinstance(commands, dict) and commands:
            lines.append("Entries:")
            for command_name in sorted(commands.keys()):
                lines.append(f"  - {command_name}")
        else:
            lines.append("This category is empty.")
        self.info.delete("1.0", END)
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

    def move_command(self):
        source_category = self.selected_category_name()
        if not source_category:
            messagebox.showerror("Category Editor", "Select a source category first.")
            return

        categories = self.get_categories()
        commands = categories.get(source_category, {})
        if not isinstance(commands, dict) or not commands:
            messagebox.showerror("Category Editor", "Selected category has no commands to move.")
            return

        available_commands = sorted(commands.keys())
        target_categories = [name for name in sorted(categories.keys()) if name != source_category]

        if not target_categories:
            messagebox.showerror("Category Editor", "No other categories exist yet.")
            return

        dialog = MoveCommandDialog(
            self.window,
            source_category,
            available_commands,
            target_categories,
        )
        values = dialog.show()
        if values is None:
            return

        command_name = values.get("command_name", "")
        target_category = values.get("target_category", "")

        if not command_name or command_name not in commands:
            messagebox.showerror("Category Editor", "Invalid command selection.")
            return

        if not target_category or target_category not in categories:
            messagebox.showerror("Category Editor", "Invalid target category selection.")
            return

        if command_name in categories[target_category]:
            if not messagebox.askokcancel(
                "Overwrite Command",
                f"'{command_name}' already exists in '{target_category}'.\n\nOverwrite it?"
            ):
                return

        categories[target_category][command_name] = commands.pop(command_name)

        self.app.persist_categories()
        self.app.rebuild_category_buttons()
        self.app.set_status(
            f"Moved command {command_name} from {source_category} to {target_category}"
        )
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

    def get_windows_dict(self) -> dict:
        windows = getattr(self.cfg, "Windows", None)
        if windows is None or not isinstance(windows, dict):
            windows = {}
            setattr(self.cfg, "Windows", windows)
        return windows

    def persist_windows(self) -> None:
        self.persist_full_config()

    def persist_full_config(self) -> None:
        try:
            terminal = getattr(self.cfg, "terminal", {"application": "gnome-terminal"})
            debug = getattr(self.cfg, "debug", {"Flag": False})
            windows = getattr(self.cfg, "Windows", {})
            favorites = getattr(self.cfg, "Favorites", [])
            hotkeys = getattr(self.cfg, "Hotkeys", {})
            disabled_plugins = getattr(self.cfg, "DisabledPlugins", [])
            categories = getattr(self.cfg, "Categories", {})

            lines = [
                "# TermForge user configuration",
                "# Edit Categories below.",
                "",
                f"terminal = {pprint.pformat(terminal, indent=4)}",
                f"debug = {pprint.pformat(debug, indent=4)}",
                f"Windows = {pprint.pformat(windows, indent=4)}",
                f"Favorites = {pprint.pformat(favorites, indent=4)}",
                f"Hotkeys = {pprint.pformat(hotkeys, indent=4)}",
                f"DisabledPlugins = {pprint.pformat(disabled_plugins, indent=4)}",
                f"Categories = {pprint.pformat(categories, indent=4)}",
                "",
            ]

            CONFIG_FILE.write_text("\n".join(lines), encoding="utf-8")
        except Exception as exc:
            self.log(f"Could not persist full config: {exc}")

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

    def get_hotkeys_dict(self) -> dict:
        hotkeys = getattr(self.cfg, "Hotkeys", None)
        if hotkeys is None or not isinstance(hotkeys, dict):
            hotkeys = {}
            setattr(self.cfg, "Hotkeys", hotkeys)
        return hotkeys

    def open_hotkey_editor(self) -> None:
        HotkeyEditorWindow(self)

    def persist_hotkeys(self) -> None:
        self.persist_full_config()

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
                    values = self.resolve_shared_vars(names)
                    if values is None:
                        runner.step_failed("Chain cancelled during shared vars.")
                        return
                    shared_vars.update(values)
                    runner.step_done(f"Shared vars captured: {', '.join(names)}")
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
                    step_cmd = self.resolve_command_placeholders(step_cmd, shared_vars=shared_vars)
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

        def refresh() -> None:
            listbox.delete(0, END)
            for entry in self.command_history:
                label = f"{entry.get('timestamp','')}  [{entry.get('action_type','')}] {entry.get('command','')}"
                listbox.insert(END, label)
            info.delete("1.0", END)
            info.insert("1.0", "Select a history entry to inspect or rerun.\n")

        def show_selected(_event=None) -> None:
            idxs = listbox.curselection()
            if not idxs:
                return
            entry = self.command_history[idxs[0]]
            selected_entry["value"] = entry
            lines = [
                f"Time: {entry.get('timestamp','')}",
                f"Action: {entry.get('action_type','')}",
                f"Source: {entry.get('source','')}",
                f"Window ID: {entry.get('window_id','')}",
                "",
                "Command:",
                entry.get("command", ""),
            ]
            lines.append("")
            lines.append("Use 'Move Command' to move one of these into another category.")
            info.delete("1.0", END)
            info.insert("1.0", "\n".join(lines))

        def rerun_selected() -> None:
            entry = selected_entry["value"]
            if not entry:
                self.set_status("Select a history entry first.")
                return
            self.run_cmd(entry.get("action_type"), entry.get("command"), {}, None)

        def clear_history() -> None:
            if not messagebox.askokcancel("Clear History", "Clear saved command history?"):
                return
            self.command_history = []
            self.save_state()
            refresh()
            self.set_status("Command history cleared.")

        buttons = Frame(outer)
        buttons.pack(fill=X, pady=(8, 0))
        Button(buttons, text="Rerun Selected", command=rerun_selected, bg="#2f5597", fg="white", width=16).pack(side=LEFT, padx=(0, 6))
        Button(buttons, text="Clear History", command=clear_history, bg="#7f6000", fg="white", width=16).pack(side=LEFT, padx=(0, 6))
        Button(buttons, text="Close", command=win.destroy, bg="red", fg="black", width=16).pack(side=RIGHT)

        listbox.bind("<<ListboxSelect>>", show_selected)
        refresh()

    def parse_command_entry_public(self, entry):
        return parse_command_entry(entry)

    def persist_categories(self) -> None:
        self.persist_full_config()

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

    def build_menu(self) -> None:
        menubar = Menu(self.root)

        file_menu = Menu(menubar, tearoff=0)
        file_menu.add_command(label="Exit", command=self.on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        tools_menu = Menu(menubar, tearoff=0)
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
            favorites_frame = Frame(frame)
            favorites_frame.pack(fill=X, pady=(0, 8))
            for category, subcategory in favorites:
                Button(
                    favorites_frame,
                    text=subcategory,
                    width=13,
                    bg="#1f4e79",
                    fg="white",
                    command=lambda c=category, s=subcategory: self.run_favorite(c, s),
                ).pack(side=LEFT, padx=2, pady=2)

        search_row = Frame(frame)
        search_row.pack(fill=X, pady=(0, 8))
        Label(search_row, text="Search:", width=8, anchor="w").pack(side=LEFT)
        search_entry = Entry(search_row, textvariable=self.search_var, width=22)
        search_entry.pack(side=LEFT, fill=X, expand=True)
        Button(search_row, text="Go", width=6, command=self.open_search_results, bg="navy", fg="white").pack(side=LEFT, padx=(6, 0))
        Button(search_row, text="Clear", width=6, command=self.clear_search, bg="gray", fg="white").pack(side=LEFT, padx=(6, 0))
        self.search_var.trace_add("write", self.update_category_filter)
        search_entry.bind("<Return>", self.open_search_results)

        self.categories_frame = Frame(frame)
        self.categories_frame.pack()
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

        Label(
            frame,
            text="Use the Tools menu for windows, history, plugins, and hotkeys.",
            width=44,
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
            wraplength=320,
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
