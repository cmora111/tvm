from __future__ import annotations

import importlib.util
import json
import logging
import re
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from tkinter import (
    BOTH, END, LEFT, RIGHT, X, Y,
    Button, Entry, Frame, Label, Listbox, Scrollbar,
    StringVar, Text, Tk, Toplevel, messagebox,
)

APP_NAME = "TVM"
APP_VERSION = "0.3.2"
PLUGIN_API_VERSION = 1
MAX_HISTORY = 30

CONFIG_DIR = Path.home() / ".config" / "tvm"
CONFIG_FILE = CONFIG_DIR / "config.py"
PLUGIN_DIR = CONFIG_DIR / "plugins"
STATE_FILE = CONFIG_DIR / "state.json"
LOG_FILE = CONFIG_DIR / "tvm.log"
HELPER_TIMEOUT_SECONDS = 20
PLACEHOLDER_RE = re.compile(r"<([^<>]+)>")

CONFIG_DIR.mkdir(parents=True, exist_ok=True)
PLUGIN_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


class TVMError(RuntimeError):
    pass


def load_config():
    if CONFIG_FILE.exists():
        spec = importlib.util.spec_from_file_location("tvm_user_config", CONFIG_FILE)
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
        "# TVM user configuration",
        "# Edit Categories below.",
        "",
        f"terminal = {repr(getattr(default_config, 'terminal', {'application': 'gnome-terminal'}))}",
        f"debug = {repr(getattr(default_config, 'debug', {'Flag': False}))}",
        f"Categories = {repr(getattr(default_config, 'Categories', {}))}",
        "Favorites = []",
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
    def __init__(self, parent, title: str, fields: list[str], defaults: dict[str, str] | None = None):
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

        Label(container, text="Enter command values", bd=2, relief="groove", width=28, bg="lightgreen", fg="black").pack(pady=(0, 10))

        self.entries: dict[str, Entry] = {}
        for field in fields:
            row = Frame(container)
            row.pack(fill=X, pady=3)
            Label(row, text=f"{field}:", width=12, anchor="w").pack(side=LEFT)
            entry = Entry(row, width=36)
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
    def __init__(self, parent, title: str, steps: list[str]):
        self.window = Toplevel(parent)
        self.window.title(title)
        self.window.geometry("760x360")
        self.window.transient(parent)

        outer = Frame(self.window, padx=8, pady=8)
        outer.pack(fill=BOTH, expand=True)

        Label(
            outer,
            text=title,
            bd=4,
            width=40,
            bg="lightgreen",
            fg="black",
            relief="raised",
        ).pack(pady=(0, 8))

        body = Frame(outer)
        body.pack(fill=BOTH, expand=True)

        self.listbox = Listbox(body, width=80, height=14)
        self.listbox.pack(side=LEFT, fill=BOTH, expand=True)

        scrollbar = Scrollbar(body, command=self.listbox.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.listbox.config(yscrollcommand=scrollbar.set)

        self.lines = list(steps)
        for line in self.lines:
            self.listbox.insert(END, f"[ ] {line}")

        self.status_var = StringVar(value="Waiting to start...")
        Label(outer, textvariable=self.status_var, anchor="w").pack(fill=X, pady=(8, 4))
        Button(outer, text="Close", width=14, bg="red", fg="black", command=self.window.destroy).pack(anchor="e")

    def _set_row(self, index: int, prefix: str, text: str):
        if index < 0 or index >= len(self.lines):
            return
        self.lines[index] = text
        self.listbox.delete(index)
        self.listbox.insert(index, f"{prefix} {text}")
        self.listbox.selection_clear(0, END)
        self.listbox.selection_set(index)
        self.listbox.see(index)
        self.window.update_idletasks()

    def mark_running(self, index: int, text: str):
        self.status_var.set(f"Running step {index + 1}: {text}")
        self._set_row(index, "[>]", text)

    def mark_done(self, index: int, text: str):
        self.status_var.set(f"Completed step {index + 1}: {text}")
        self._set_row(index, "[✓]", text)

    def mark_failed(self, index: int, text: str, error: str):
        self.status_var.set(f"Failed step {index + 1}: {error}")
        self._set_row(index, "[x]", text)

    def finish(self, success: bool = True):
        self.status_var.set("Chain complete." if success else "Chain stopped due to error.")
        self.window.update_idletasks()


class TVMApp:
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

        if self.debug:
            logging.getLogger().setLevel(logging.DEBUG)

        self.load_state()
        self.log("Starting TVM")
        self.load_plugins(force=True)
        self.build_main()
        self.root.after(250, self.safe_initial_select)

    def log(self, message: str) -> None:
        if self.debug:
            print(message)
        logging.info(message)

    def set_status(self, message: str) -> None:
        self.status_var.set(message)
        self.log(message)

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

    def remember_window(self, window_id) -> None:
        self.window_id = window_id
        self.last_window_id = window_id
        self.save_state()

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

    def on_close(self) -> None:
        self.save_state()
        self.log("Shutting down TVM")
        try:
            self.root.quit()
        finally:
            self.root.destroy()

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

    def _read_plugin_metadata(self, module, file: Path) -> dict:
        api_version = getattr(module, "TVM_PLUGIN_API_VERSION", PLUGIN_API_VERSION)
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

    def open_plugin_browser(self) -> None:
        self.load_plugins(force=False)
        win = Toplevel(self.root)
        win.title("Plugin Browser")
        win.geometry("900x420")
        win.protocol("WM_DELETE_WINDOW", win.destroy)

        outer = Frame(win, padx=8, pady=8)
        outer.pack(fill=BOTH, expand=True)

        Label(
            outer,
            text=f"Plugin Browser — API v{PLUGIN_API_VERSION}",
            bd=4,
            width=40,
            bg="lightgreen",
            fg="black",
            relief="raised",
        ).pack(pady=(0, 8))

        body = Frame(outer)
        body.pack(fill=BOTH, expand=True)

        left = Frame(body)
        left.pack(side=LEFT, fill=Y)

        right = Frame(body)
        right.pack(side=RIGHT, fill=BOTH, expand=True, padx=(8, 0))

        listbox = Listbox(left, width=36, height=18)
        listbox.pack(side=LEFT, fill=Y)

        scrollbar = Scrollbar(left, command=listbox.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        listbox.config(yscrollcommand=scrollbar.set)

        status_var = StringVar(value="Select a plugin to inspect.")
        info = Text(right, wrap="word", width=72, height=20)
        info.pack(fill=BOTH, expand=True)
        Label(right, textvariable=status_var, anchor="w").pack(fill=X, pady=(6, 0))

        snapshot = []

        def get_plugin_snapshot():
            rows = []
            names = sorted(set(self.plugins.keys()) | set(self.plugin_errors.keys()))
            for name in names:
                file = PLUGIN_DIR / f"{name}.py"
                mtime = "unknown"
                if file.exists():
                    mtime = datetime.fromtimestamp(file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                if name in self.plugins:
                    meta = getattr(self.plugins[name], "__tvm_metadata__", {})
                    rows.append({
                        "display_name": meta.get("display_name", name),
                        "name": name,
                        "status": "loaded",
                        "plugin_version": meta.get("plugin_version", "0.1.0"),
                        "api_version": meta.get("api_version", PLUGIN_API_VERSION),
                        "compatible": meta.get("compatible", True),
                        "description": meta.get("description", ""),
                        "path": str(file),
                        "mtime": mtime,
                        "error": "",
                    })
                else:
                    rows.append({
                        "display_name": name,
                        "name": name,
                        "status": "error",
                        "plugin_version": "unknown",
                        "api_version": "unknown",
                        "compatible": False,
                        "description": "",
                        "path": str(file),
                        "mtime": mtime,
                        "error": self.plugin_errors.get(name, "Unknown plugin load error."),
                    })
            return rows

        def refresh_list() -> None:
            self.load_plugins(force=False)
            listbox.delete(0, END)
            snapshot.clear()
            snapshot.extend(get_plugin_snapshot())
            for item in snapshot:
                prefix = "✓" if item["status"] == "loaded" else "✗"
                listbox.insert(END, f"{prefix} {item['display_name']}  [api {item['api_version']}]")
            info.delete("1.0", END)
            info.insert("1.0", "Select a plugin to inspect.\n")
            status_var.set(f"{len(snapshot)} plugin file(s) found.")

        def show_selected(_event=None) -> None:
            idxs = listbox.curselection()
            if not idxs:
                return
            item = snapshot[idxs[0]]
            lines = [
                f"Name: {item['display_name']}",
                f"Internal name: {item['name']}",
                f"Status: {item['status']}",
                f"Plugin version: {item['plugin_version']}",
                f"Plugin API version: {item['api_version']}",
                f"Compatible with TVM: {item['compatible']}",
                f"Path: {item['path']}",
                f"Last modified: {item['mtime']}",
                "",
            ]
            if item["description"]:
                lines.extend(["Description:", item["description"], ""])
            if item["error"]:
                lines.extend(["Load error:", item["error"], ""])
            info.delete("1.0", END)
            info.insert("1.0", "\n".join(lines))
            status_var.set(f"Viewing: {item['display_name']}")

        buttons = Frame(outer)
        buttons.pack(fill=X, pady=(8, 0))

        Button(buttons, text="Reload", command=refresh_list, bg="navy", fg="white", width=16).pack(side=LEFT, padx=(0, 6))
        Button(buttons, text="Open Plugin Folder", command=self.open_plugin_folder, bg="darkgreen", fg="white", width=16).pack(side=LEFT, padx=(0, 6))
        Button(buttons, text="Close", command=win.destroy, bg="red", fg="black", width=16).pack(side=RIGHT)

        listbox.bind("<<ListboxSelect>>", show_selected)
        refresh_list()

    def load_plugins(self, force: bool = False) -> dict[str, object]:
        plugins: dict[str, object] = {}
        mtimes: dict[str, float] = {}
        errors: dict[str, str] = {}
        for file in sorted(PLUGIN_DIR.glob("*.py")):
            name = file.stem
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
                spec = importlib.util.spec_from_file_location(f"tvm_plugin_{name}", file)
                if spec is None or spec.loader is None:
                    raise TVMError("Could not create plugin spec.")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                metadata = self._read_plugin_metadata(module, file)
                setattr(module, "__tvm_metadata__", metadata)
                if not metadata["compatible"]:
                    raise TVMError(f"Unsupported plugin API version {metadata['api_version']}. This TVM build supports API {PLUGIN_API_VERSION}.")
                if not metadata["has_run"]:
                    raise TVMError("Plugin does not define run(app, context).")
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
        old_names = set(self.plugins)
        old_mtimes = dict(self.plugin_mtimes)
        old_errors = dict(self.plugin_errors)
        self.load_plugins(force=False)
        new_names = set(self.plugins)
        added = sorted(new_names - old_names)
        removed = sorted(old_names - new_names)
        changed = sorted(name for name in (new_names & old_names) if self.plugin_mtimes.get(name) != old_mtimes.get(name))
        failed = sorted(name for name in self.plugin_errors if old_errors.get(name) != self.plugin_errors.get(name))
        parts = []
        if added:
            parts.append(f"Added: {', '.join(added)}")
        if changed:
            parts.append(f"Reloaded: {', '.join(changed)}")
        if removed:
            parts.append(f"Removed: {', '.join(removed)}")
        if failed:
            parts.append(f"Errors: {', '.join(failed)}")
        if not parts:
            parts.append("No plugin changes detected.")
        self.set_status("Plugins reloaded.")
        messagebox.showinfo("Plugins", "\n".join(parts))

    def get_plugin_snapshot(self) -> list[dict]:
        snapshot = []
        names = sorted(set(self.plugins.keys()) | set(self.plugin_errors.keys()))
        for name in names:
            file = PLUGIN_DIR / f"{name}.py"
            mtime = "unknown"
            if file.exists():
                mtime = datetime.fromtimestamp(file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            if name in self.plugins:
                meta = getattr(self.plugins[name], "__tvm_metadata__", {})
                snapshot.append({
                    "display_name": meta.get("display_name", name),
                    "name": name,
                    "status": "loaded",
                    "plugin_version": meta.get("plugin_version", "0.1.0"),
                    "api_version": meta.get("api_version", PLUGIN_API_VERSION),
                    "compatible": meta.get("compatible", True),
                    "description": meta.get("description", ""),
                    "path": str(file),
                    "mtime": mtime,
                    "error": "",
                })
            else:
                snapshot.append({
                    "display_name": name,
                    "name": name,
                    "status": "error",
                    "plugin_version": "unknown",
                    "api_version": "unknown",
                    "compatible": False,
                    "description": "",
                    "path": str(file),
                    "mtime": mtime,
                    "error": self.plugin_errors.get(name, "Unknown plugin load error."),
                })
        return snapshot

    def open_plugin_folder(self) -> None:
        try:
            if sys.platform.startswith("linux"):
                subprocess.Popen(["xdg-open", str(PLUGIN_DIR)])
            else:
                raise TVMError("Opening the plugin folder is only implemented for Linux.")
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
            raise TVMError("Plugin command must be a plugin name or dict.")
        if not plugin_name:
            raise TVMError("Plugin command did not specify a plugin name.")
        plugin = self.plugins.get(plugin_name)
        if plugin is None:
            load_error = self.plugin_errors.get(plugin_name)
            if load_error:
                raise TVMError(f"Plugin '{plugin_name}' failed to load: {load_error}")
            raise TVMError(f"Plugin '{plugin_name}' was not found in {PLUGIN_DIR}.")
        run_fn = getattr(plugin, "run", None)
        if not callable(run_fn):
            raise TVMError(f"Plugin '{plugin_name}' does not define run(app, context).")
        context = {"window_id": self.window_id, "config": self.cfg, "plugin_dir": PLUGIN_DIR, "args": plugin_args.get("args", plugin_args), "app_version": APP_VERSION, "plugin_api_version": PLUGIN_API_VERSION}
        self.set_status(f"Running plugin: {plugin_name}")
        self.add_history_entry("plugin", plugin_name, source="plugin")
        run_fn(self, context)

    def resolve_command_placeholders(self, cmd: str, shared_vars: dict[str, str] | None = None):
        if not isinstance(cmd, str):
            return cmd
        shared_vars = shared_vars or {}
        seen = set()
        prompt_fields = []
        for field_name in PLACEHOLDER_RE.findall(cmd):
            if field_name in shared_vars:
                continue
            if field_name not in seen:
                seen.add(field_name)
                prompt_fields.append(field_name)

        values = dict(shared_vars)
        if prompt_fields:
            prompt = MultiFieldPrompt(self.root, "Command Input", prompt_fields)
            entered = prompt.show()
            if entered is None:
                self.set_status("Command cancelled.")
                return None
            values.update(entered)

        resolved = cmd
        for field_name in PLACEHOLDER_RE.findall(cmd):
            resolved = resolved.replace(f"<{field_name}>", values.get(field_name, ""))
        return resolved

    def confirm_command(self, cmd_type, cmd, options):
        if not options.get("confirm", False):
            return True
        msg = f"About to run:\n\n{cmd}\n\nType: {cmd_type}"
        if cmd_type == 2 or cmd_type == "command" or cmd_type == "send":
            msg += f"\nTarget window: {self.window_id}"
        return messagebox.askokcancel("Confirm Command", msg)

    def _run_helper(self, payload: dict) -> dict:
        command = [sys.executable, "-m", "tvm.xdo_helper"]
        self.log(f"Running helper action={payload.get('action')} payload={payload}")
        proc = subprocess.run(command, input=json.dumps(payload), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=HELPER_TIMEOUT_SECONDS, check=False)
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        if stderr:
            logging.warning("helper stderr: %s", stderr)
        if proc.returncode != 0 and not stdout:
            raise TVMError(f"Helper exited with code {proc.returncode}" + (f": {stderr}" if stderr else ""))
        if not stdout:
            raise TVMError("Helper returned no data.")
        result = json.loads(stdout)
        if result.get("status") != "ok":
            raise TVMError(result.get("error", "Helper reported an unknown error."))
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
            raise TVMError("No window selected.")
        self.remember_window(selected)
        self.set_status(f"Selected window: {self.window_id}")

    def select_target_window_with_notice(self) -> None:
        try:
            self.select_target_window()
            messagebox.showinfo("Target Window", f"Selected window id: {self.window_id}")
        except Exception as exc:
            self.show_error("Target Window", str(exc))

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

    def send_to_selected_window(self, cmd: str) -> None:
        if not self.window_id:
            raise TVMError("No target window selected.")
        self.set_status(f"Sending to window {self.window_id}: {cmd}")
        result = self._run_helper({"action": "send", "window_id": self.window_id, "text": cmd, "key": "Return", "focus_delay_ms": 150})
        active_window = result.get("active_window")
        self.remember_window(self.window_id)
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

    def select_profile(self, name):
        windows = getattr(self.cfg, "Windows", None)
        if windows is None or not isinstance(windows, dict):
            windows = {}
            setattr(self.cfg, "Windows", windows)

        saved = windows.get(name)
        if saved and self.validate_window_id(saved):
            self.window_id = saved
            self.set_status(f"Using profile '{name}' -> {saved}")
            return

        self.set_status(f"Select window for profile '{name}'")
        self.select_target_window()
        windows[name] = self.window_id

        try:
            import pprint
            text = CONFIG_FILE.read_text(encoding="utf-8")
            new_windows = pprint.pformat(windows, indent=4)
            if re.search(r"(?m)^Windows\s*=", text):
                text = re.sub(r"(?ms)^Windows\s*=\s*{.*?}(?=^\S|\Z)", f"Windows = {new_windows}\n", text)
            else:
                text += f"\n\nWindows = {new_windows}\n"
            CONFIG_FILE.write_text(text, encoding="utf-8")
        except Exception as exc:
            self.log(f"Could not persist window profile: {exc}")

    def run_sleep(self, seconds):
        self.set_status(f"Sleeping {seconds}s...")
        time.sleep(float(seconds))

    def resolve_shared_vars(self, names: list[str]) -> dict[str, str] | None:
        prompt = MultiFieldPrompt(self.root, "Shared Variables", names)
        values = prompt.show()
        if values is None:
            self.set_status("Chain cancelled.")
            return None
        return values

    def run_chain(self, steps, source="chain") -> None:
        if not isinstance(steps, (list, tuple)) or not steps:
            raise TVMError("Chain command requires a non-empty list of steps.")

        total = len(steps)
        shared_vars: dict[str, str] = {}

        for index, step in enumerate(steps, start=1):
            if not isinstance(step, (list, tuple)) or not step:
                raise TVMError(f"Invalid chain step: {step!r}")

            step_kind = step[0]

            if step_kind == "vars":
                if len(step) < 2 or not isinstance(step[1], (list, tuple)):
                    raise TVMError("vars step requires a list of variable names.")
                names = [str(name) for name in step[1]]
                self.set_status(f"Chain step {index}/{total}: shared vars")
                values = self.resolve_shared_vars(names)
                if values is None:
                    return
                shared_vars.update(values)
                continue

            if step_kind == "sleep":
                if len(step) < 2:
                    raise TVMError("Sleep step requires a number of seconds.")
                self.set_status(f"Chain step {index}/{total}: sleep {step[1]}")
                self.run_sleep(step[1])
                continue

            if step_kind == "select_profile":
                if len(step) < 2:
                    raise TVMError("select_profile step requires a profile name.")
                self.set_status(f"Chain step {index}/{total}: select profile {step[1]}")
                self.select_profile(step[1])
                continue

            step_type, step_cmd, step_options = parse_command_entry(step)
            self.set_status(f"Chain step {index}/{total}: {step_cmd}")
            self.run_cmd(step_type, step_cmd, step_options, None, record_history=False, shared_vars=shared_vars)

        self.add_history_entry("chain", f"{total} steps", source=source)
        self.set_status(f"Chain complete: {total} step(s).")

    def run_cmd(self, cmd_type, cmd, options=None, current_window=None, record_history: bool = True, shared_vars: dict[str, str] | None = None, raise_on_error: bool = False) -> None:
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
            if normalized == 0 or normalized == "select":
                self.select_target_window()
            elif normalized == 1 or normalized == "spawn":
                self.spawn_terminal(str(resolved_cmd), record_history=record_history)
            elif normalized == 2 or normalized == "command" or normalized == "send":
                self.send_to_selected_window(str(resolved_cmd))
            elif normalized == 3 or normalized == "detached":
                self.run_detached(str(resolved_cmd), record_history=record_history)
            elif normalized == "plugin":
                self.run_plugin(cmd)
            else:
                raise TVMError(f"Unknown command type: {cmd_type}")
        except Exception as exc:
            if raise_on_error:
                raise
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
        Label(win, text=f"Matches for: {query}", bd=4, width=40, bg="lightgreen", fg="black", relief="raised").pack(padx=8, pady=(8, 6))
        if not results:
            Label(win, text="No matching commands found.").pack(padx=8, pady=8)
        else:
            for category, subcategory in results:
                Button(win, text=f"{category} → {subcategory}", width=40, bg="black", fg="yellow", command=lambda c=category, s=subcategory, w=win: self.select_cmd(w, c, s)).pack(pady=2, padx=8)
        Button(win, text="Close", width=40, bg="red", fg="black", command=win.destroy).pack(pady=(8, 8))

    def clear_search(self) -> None:
        self.search_var.set("")
        self.update_category_filter()

    def build_main(self) -> None:
        frame = Frame(self.root, padx=8, pady=8)
        frame.pack()
        Label(frame, text=f"{APP_NAME} {APP_VERSION}", bd=4, width=28, bg="lightgreen", fg="black", relief="raised").pack(pady=(0, 8))

        favorites = self.get_favorites()
        if favorites:
            Label(frame, text="Favorites", width=28, bg="#d9edf7", fg="black", relief="groove").pack(pady=(0, 4))
            favorites_frame = Frame(frame)
            favorites_frame.pack(fill=X, pady=(0, 8))
            for category, subcategory in favorites:
                Button(favorites_frame, text=subcategory, width=13, bg="#1f4e79", fg="white", command=lambda c=category, s=subcategory: self.run_favorite(c, s)).pack(side=LEFT, padx=2, pady=2)

        search_row = Frame(frame)
        search_row.pack(fill=X, pady=(0, 8))
        Label(search_row, text="Search:", width=8, anchor="w").pack(side=LEFT)
        search_entry = Entry(search_row, textvariable=self.search_var, width=22)
        search_entry.pack(side=LEFT, fill=X, expand=True)
        Button(search_row, text="Go", width=6, command=self.open_search_results, bg="navy", fg="white").pack(side=LEFT, padx=(6, 0))
        Button(search_row, text="Clear", width=6, command=self.clear_search, bg="gray", fg="white").pack(side=LEFT, padx=(6, 0))
        self.search_var.trace_add("write", self.update_category_filter)
        search_entry.bind("<Return>", self.open_search_results)

        categories_frame = Frame(frame)
        categories_frame.pack()
        self.category_buttons = {}
        categories = getattr(self.cfg, "Categories", {})
        for category in categories:
            btn = Button(categories_frame, text=category, width=28, bg="black", fg="yellow", command=lambda c=category: self.open_category(c))
            btn.pack(pady=2)
            self.category_buttons[category] = btn

        Button(frame, text="Reuse Saved Window", width=28, bg="#2f5597", fg="white", command=self.reuse_last_window).pack(pady=(8, 2))
        Button(frame, text="Forget Saved Window", width=28, bg="#7f6000", fg="white", command=self.forget_saved_window).pack(pady=2)
        Button(frame, text="Select Target Window", width=28, bg="darkgreen", fg="white", command=self.select_target_window_with_notice).pack(pady=2)
        Button(frame, text="Plugin Folder", width=28, bg="purple", fg="white", command=self.open_plugin_folder).pack(pady=2) 
        Button(frame, text="Reload Plugins", width=28, bg="navy", fg="white", command=self.reload_plugins_with_notice).pack(pady=2)
        Button(frame, text="Exit", width=28, bg="red", fg="black", command=self.on_close).pack(pady=(8, 4))
        Label(frame, textvariable=self.status_var, anchor="w", justify="left", width=40, wraplength=320, bg="#f0f0f0", fg="black", relief="sunken", padx=6, pady=4).pack(fill=X, pady=(4, 0))

    def open_category(self, category: str) -> None:
        win = Toplevel(self.root)
        win.title(category)
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        Label(win, text=category, bd=4, width=28, bg="lightgreen", fg="black", relief="raised").pack(padx=8, pady=(8, 6))
        for subcategory in self.cfg.Categories[category]:
            Button(win, text=subcategory, width=28, bg="black", fg="yellow", command=lambda c=category, s=subcategory, w=win: self.select_cmd(w, c, s)).pack(pady=2, padx=8)
        Button(win, text="Close", width=28, bg="red", fg="black", command=win.destroy).pack(pady=(8, 8))

    @staticmethod
    def show_error(title: str, message: str) -> None:
        messagebox.showerror(title, message)


def main() -> int:
    ensure_user_config()
    cfg = load_config()
    root = Tk()
    TVMApp(root, cfg)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
