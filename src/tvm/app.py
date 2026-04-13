from __future__ import annotations

import importlib.util
import json
import logging
import re
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path
from tkinter import (
    BOTH,
    END,
    LEFT,
    RIGHT,
    Y,
    Button,
    Frame,
    Label,
    Listbox,
    Scrollbar,
    StringVar,
    Text,
    Tk,
    Toplevel,
    messagebox,
    simpledialog,
)

APP_NAME = "TVM"
APP_VERSION = "0.2.4"
PLUGIN_API_VERSION = 1

CONFIG_DIR = Path.home() / ".config" / "tvm"
CONFIG_FILE = CONFIG_DIR / "config.py"
PLUGIN_DIR = CONFIG_DIR / "plugins"
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


class TVMApp:
    def __init__(self, root: Tk, cfg) -> None:
        self.root = root
        self.cfg = cfg
        self.root.title(f"{APP_NAME} {APP_VERSION}")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.window_id: int | str | None = None
        self.plugins: dict[str, object] = {}
        self.plugin_mtimes: dict[str, float] = {}
        self.plugin_errors: dict[str, str] = {}

        self.debug = bool(getattr(cfg, "debug", {}).get("Flag", False))
        self.application = getattr(cfg, "terminal", {}).get("application", "gnome-terminal")
        self.status_var = StringVar(value="Ready.")

        if self.debug:
            logging.getLogger().setLevel(logging.DEBUG)

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

    def on_close(self) -> None:
        self.log("Shutting down TVM")
        try:
            self.root.quit()
        finally:
            self.root.destroy()

    # ----------------------------
    # Plugin support
    # ----------------------------

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
                    raise TVMError(
                        f"Unsupported plugin API version {metadata['api_version']}. "
                        f"This TVM build supports API {PLUGIN_API_VERSION}."
                    )
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
        changed = sorted(
            name for name in (new_names & old_names)
            if self.plugin_mtimes.get(name) != old_mtimes.get(name)
        )
        failed = sorted(
            name for name in self.plugin_errors
            if old_errors.get(name) != self.plugin_errors.get(name)
        )

        parts: list[str] = []
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
        snapshot: list[dict] = []
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
        Label(right, textvariable=status_var, anchor="w").pack(fill="x", pady=(6, 0))

        snapshot: list[dict] = []

        def refresh_list() -> None:
            self.load_plugins(force=False)
            listbox.delete(0, END)
            snapshot.clear()
            snapshot.extend(self.get_plugin_snapshot())
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
            if item["status"] == "loaded":
                lines.extend([
                    "Expected entry point:",
                    "def run(app, context): ...",
                    "",
                    "Context keys: window_id, config, plugin_dir, args, app_version, plugin_api_version",
                ])
            info.delete("1.0", END)
            info.insert("1.0", "\n".join(lines))
            status_var.set(f"Viewing: {item['display_name']}")

        buttons = Frame(outer)
        buttons.pack(fill="x", pady=(8, 0))
        Button(buttons, text="Reload", command=refresh_list, bg="navy", fg="white", width=16).pack(side=LEFT, padx=(0, 6))
        Button(buttons, text="Open Plugin Folder", command=self.open_plugin_folder, bg="darkgreen", fg="white", width=16).pack(side=LEFT, padx=(0, 6))
        Button(buttons, text="Close", command=win.destroy, bg="red", fg="black", width=16).pack(side=RIGHT)

        listbox.bind("<<ListboxSelect>>", show_selected)
        refresh_list()

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

        context = {
            "window_id": self.window_id,
            "config": self.cfg,
            "plugin_dir": PLUGIN_DIR,
            "args": plugin_args.get("args", plugin_args),
            "app_version": APP_VERSION,
            "plugin_api_version": PLUGIN_API_VERSION,
        }
        self.set_status(f"Running plugin: {plugin_name}")
        run_fn(self, context)

    # ----------------------------
    # Placeholder / confirmation support
    # ----------------------------

    def resolve_command_placeholders(self, cmd: str):
        if not isinstance(cmd, str):
            return cmd

        seen: set[str] = set()
        ordered_fields: list[str] = []
        for field_name in PLACEHOLDER_RE.findall(cmd):
            if field_name not in seen:
                seen.add(field_name)
                ordered_fields.append(field_name)

        if not ordered_fields:
            return cmd

        resolved = cmd
        for field_name in ordered_fields:
            user_value = simpledialog.askstring(
                "Command Input",
                f"Enter value for {field_name}:",
                parent=self.root,
            )
            if user_value is None:
                self.set_status(f"Command cancelled at placeholder <{field_name}>.")
                return None
            resolved = resolved.replace(f"<{field_name}>", user_value)
        return resolved

    def confirm_command(self, cmd_type, cmd, options):
        if not options.get("confirm", False):
            return True

        msg = f"About to run:\n\n{cmd}\n\nType: {cmd_type}"
        if cmd_type == 2 or cmd_type == "command" or cmd_type == "send":
            msg += f"\nTarget window: {self.window_id}"
        return messagebox.askokcancel("Confirm Command", msg)

    # ----------------------------
    # Window/helper integration
    # ----------------------------

    def _run_helper(self, payload: dict) -> dict:
        command = [sys.executable, "-m", "tvm.xdo_helper"]
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
            raise TVMError("Helper timed out.") from exc
        except Exception as exc:
            raise TVMError(f"Could not start helper: {exc}") from exc

        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()

        if stderr:
            logging.warning("helper stderr: %s", stderr)

        if proc.returncode != 0 and not stdout:
            raise TVMError(f"Helper exited with code {proc.returncode}" + (f": {stderr}" if stderr else ""))

        if not stdout:
            raise TVMError("Helper returned no data.")

        try:
            result = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise TVMError(f"Helper returned invalid JSON: {stdout!r}") from exc

        if result.get("status") != "ok":
            raise TVMError(result.get("error", "Helper reported an unknown error."))

        return result

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

        self.window_id = selected
        self.set_status(f"Selected window: {self.window_id}")

    def select_target_window_with_notice(self) -> None:
        try:
            self.select_target_window()
            messagebox.showinfo("Target Window", f"Selected window id: {self.window_id}")
        except Exception as exc:
            self.show_error("Target Window", str(exc))

    def safe_initial_select(self) -> None:
        try:
            self.select_target_window()
        except Exception as exc:
            self.log(f"Initial selection skipped: {exc}")

    def send_to_selected_window(self, cmd: str) -> None:
        if not self.window_id:
            raise TVMError("No target window selected.")

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
            active_window = result.get("active_window")
            self.set_status(f"Sent to selected window {self.window_id} (active {active_window}).")
        except TVMError as exc:
            logging.warning("Send failed for window %s: %s", self.window_id, exc)
            self.window_id = None
            raise TVMError(
                "Could not send command to the selected window. "
                "The target may have closed, activation may have failed, or the X11 helper failed. "
                "Re-select the window and try again."
            ) from exc

    def send_text_to_window(self, text: str) -> None:
        self.send_to_selected_window(text)

    def spawn_terminal(self, cmd: str) -> None:
        self.set_status(f"Spawning new terminal command: {cmd}")
        subprocess.Popen([self.application, "--", "bash", "-lc", cmd])

    def run_detached(self, cmd: str) -> None:
        self.set_status(f"Running detached command: {cmd}")
        subprocess.Popen(cmd, shell=True)

    # ----------------------------
    # Command dispatch
    # ----------------------------

    def run_cmd(self, cmd_type, cmd, options=None, current_window=None) -> None:
        try:
            if options is None:
                options = {}

            normalized = cmd_type
            if isinstance(cmd_type, str):
                normalized = cmd_type.strip().lower()

            resolved_cmd = cmd
            if normalized in (1, 2, 3, "spawn", "command", "send", "detached") and isinstance(cmd, str):
                resolved_cmd = self.resolve_command_placeholders(cmd)
                if resolved_cmd is None:
                    return

            if not self.confirm_command(normalized, resolved_cmd, options):
                self.set_status("Command cancelled by user.")
                return

            if normalized == 0 or normalized == "select":
                self.select_target_window()
            elif normalized == 1 or normalized == "spawn":
                self.spawn_terminal(str(resolved_cmd))
            elif normalized == 2 or normalized == "command" or normalized == "send":
                self.send_to_selected_window(str(resolved_cmd))
            elif normalized == 3 or normalized == "detached":
                self.run_detached(str(resolved_cmd))
            elif normalized == "plugin":
                self.run_plugin(cmd)
            else:
                raise TVMError(f"Unknown command type: {cmd_type}")
        except Exception as exc:
            self.show_error("Command failed", f"{exc}\n\n{traceback.format_exc()}")

    def select_cmd(self, parent_window, category: str, subcategory: str) -> None:
        entry = self.cfg.Categories[category][subcategory]
        cmd_type, cmd, options = parse_command_entry(entry)
        self.run_cmd(cmd_type, cmd, options, parent_window)

    # ----------------------------
    # Main UI
    # ----------------------------

    def build_main(self) -> None:
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

        categories = getattr(self.cfg, "Categories", {})
        for category in categories:
            Button(
                frame,
                text=category,
                width=28,
                bg="black",
                fg="yellow",
                command=lambda c=category: self.open_category(c),
            ).pack(pady=2)

        Button(
            frame,
            text="Select Target Window",
            width=28,
            bg="darkgreen",
            fg="white",
            command=self.select_target_window_with_notice,
        ).pack(pady=(8, 2))

        Button(
            frame,
            text="Plugin Browser",
            width=28,
            bg="purple",
            fg="white",
            command=self.open_plugin_browser,
        ).pack(pady=2)

        Button(
            frame,
            text="Reload Plugins",
            width=28,
            bg="navy",
            fg="white",
            command=self.reload_plugins_with_notice,
        ).pack(pady=2)

        Button(
            frame,
            text="Exit",
            width=28,
            bg="red",
            fg="black",
            command=self.on_close,
        ).pack(pady=(8, 4))

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
        ).pack(fill="x", pady=(4, 0))

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

        Button(
            win,
            text="Close",
            width=28,
            bg="red",
            fg="black",
            command=win.destroy,
        ).pack(pady=(8, 8))

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
