from __future__ import annotations

import importlib.util
import json
import logging
import re
import subprocess
import sys
import traceback
from pathlib import Path
from tkinter import Button, Entry, Frame, Label, StringVar, Tk, Toplevel, messagebox

APP_NAME = "TVM"
CONFIG_DIR = Path.home() / ".config" / "tvm"
CONFIG_FILE = CONFIG_DIR / "config.py"
PLUGIN_DIR = CONFIG_DIR / "plugins"
LOG_FILE = CONFIG_DIR / "tvm.log"
HELPER_TIMEOUT_SECONDS = 15

CONFIG_DIR.mkdir(parents=True, exist_ok=True)
PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


class TVMError(RuntimeError):
    """Application-level error for expected failures."""



def load_config():
    if CONFIG_FILE.exists():
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
        self.root.title(APP_NAME)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.debug = bool(getattr(cfg, "debug", {}).get("Flag", False))
        self.application = getattr(cfg, "terminal", {}).get("application", "gnome-terminal")
        self.window_id: int | str | None = None
        self.plugins: dict[str, object] = {}
        self.plugin_mtimes: dict[str, float] = {}
        self.load_plugins(force=True)

        if self.debug:
            logging.getLogger().setLevel(logging.DEBUG)

        self.log("TVM starting")
        if self.plugins:
            self.log(f"Loaded plugins: {', '.join(sorted(self.plugins.keys()))}")
        self.build_main()
        self.root.after(250, self.safe_initial_select)

    def log(self, msg: str) -> None:
        if self.debug:
            print(msg)
        logging.info(msg)

    def on_close(self) -> None:
        self.log("TVM shutting down")
        try:
            self.root.quit()
        finally:
            self.root.destroy()

    def load_plugins(self, force: bool = False) -> dict[str, object]:
        plugins: dict[str, object] = {}
        mtimes: dict[str, float] = {}

        if not PLUGIN_DIR.exists():
            self.plugins = {}
            self.plugin_mtimes = {}
            return self.plugins

        for file in sorted(PLUGIN_DIR.glob("*.py")):
            name = file.stem
            try:
                stat = file.stat()
                mtimes[name] = stat.st_mtime

                if not force and name in self.plugins and self.plugin_mtimes.get(name) == stat.st_mtime:
                    plugins[name] = self.plugins[name]
                    continue

                spec = importlib.util.spec_from_file_location(
                    f"tvm_user_plugin_{name}_{int(stat.st_mtime_ns)}", file
                )
                if not spec or not spec.loader:
                    raise TVMError(f"Could not load plugin spec for '{name}'.")

                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                plugins[name] = module
                self.log(f"Loaded plugin '{name}'")
            except Exception as exc:
                logging.exception("Failed to load plugin '%s' from %s", name, file)
                self.log(f"Failed to load plugin '{name}': {exc}")

        removed = sorted(set(self.plugins) - set(plugins))
        for name in removed:
            self.log(f"Removed plugin '{name}'")

        self.plugins = plugins
        self.plugin_mtimes = mtimes
        return self.plugins

    def reload_plugins(self) -> None:
        before = set(self.plugins)
        self.load_plugins(force=False)
        after = set(self.plugins)
        loaded = sorted(after - before)
        reloaded = sorted(name for name in after & before if self.plugin_mtimes.get(name))
        parts: list[str] = []
        if loaded:
            parts.append(f"new: {', '.join(loaded)}")
        if reloaded:
            parts.append(f"available: {', '.join(reloaded)}")
        if not parts:
            parts.append("No plugins found.")
        self.log("Plugin refresh complete")

    def build_main(self) -> None:
        frame = Frame(self.root, padx=8, pady=8)
        frame.pack()

        Label(
            frame,
            text="GUI CMDs",
            bd=4,
            width=20,
            bg="lightgreen",
            fg="black",
            relief="raised",
        ).pack(pady=(0, 8))

        for category in self.cfg.Categories:
            Button(
                frame,
                text=category,
                width=20,
                bg="black",
                fg="yellow",
                command=lambda c=category: self.open_category(c),
            ).pack(pady=2)

        Button(
            frame,
            text="Reload Plugins",
            width=20,
            bg="navy",
            fg="white",
            command=self.reload_plugins_with_notice,
        ).pack(pady=(8, 2))

        Button(
            frame,
            text="Exit",
            width=20,
            bg="red",
            fg="black",
            command=self.on_close,
        ).pack(side="bottom", pady=(10, 0))

    def open_category(self, category: str) -> None:
        win = Toplevel(self.root)
        win.title(category)
        win.protocol("WM_DELETE_WINDOW", win.destroy)

        Label(
            win,
            text=category,
            bd=4,
            width=20,
            bg="lightgreen",
            fg="black",
            relief="raised",
        ).pack(padx=8, pady=(8, 6))

        for subcategory in self.cfg.Categories[category]:
            Button(
                win,
                text=subcategory,
                width=20,
                bg="black",
                fg="yellow",
                command=lambda c=category, s=subcategory, w=win: self.select_cmd(w, c, s),
            ).pack(pady=2, padx=8)

        Button(
            win,
            text="Exit",
            width=20,
            bg="red",
            fg="black",
            command=win.destroy,
        ).pack(side="bottom", pady=(8, 8))

    def select_cmd(self, parent_window, category: str, subcategory: str) -> None:
        cmd_type, cmd = self.cfg.Categories[category][subcategory]
        if isinstance(cmd, str) and "" in cmd:
            self.prompt_window(cmd_type, cmd)
        else:
            self.run_cmd(cmd_type, cmd, parent_window)

    def prompt_window(self, cmd_type: int, cmd: str) -> None:
        prompt = Toplevel(self.root)
        prompt.title("Input")
        prompt.protocol("WM_DELETE_WINDOW", prompt.destroy)

        Label(prompt, text=f"Enter value for: {cmd}").pack(padx=8, pady=(8, 4))

        name_var = StringVar()
        entry = Entry(prompt, textvariable=name_var, width=40)
        entry.pack(padx=8, pady=(0, 8))
        entry.focus_set()

        def submit() -> None:
            value = name_var.get().strip()
            new_cmd = re.sub(r"", value, cmd)
            prompt.destroy()
            self.run_cmd(cmd_type, new_cmd, None)

        Button(prompt, text="OK", command=submit).pack(pady=(0, 8))
        entry.bind("<Return>", lambda _event: submit())

    def safe_initial_select(self) -> None:
        try:
            self.select_target_window()
        except Exception as exc:
            self.log(f"Initial selection skipped: {exc}")

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
            raise TVMError("helper timed out") from exc
        except Exception as exc:
            raise TVMError(f"Could not start helper: {exc}") from exc

        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        if stderr:
            logging.warning("helper stderr: %s", stderr)

        if proc.returncode != 0 and not stdout:
            raise TVMError(
                f"helper exited with code {proc.returncode}" + (f": {stderr}" if stderr else "")
            )

        if not stdout:
            raise TVMError("helper returned no data")

        try:
            result = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise TVMError(f"helper returned invalid JSON: {stdout!r}") from exc

        if result.get("status") != "ok":
            raise TVMError(result.get("error", "helper reported an unknown error"))
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
        self.log(f"Selected window: {self.window_id}")

    def run_cmd(self, cmd_type, cmd, current_window=None) -> None:
        try:
            if current_window is not None and current_window.winfo_exists():
                current_window.destroy()

            if cmd_type == 0:
                self.select_target_window()
            elif cmd_type == 1:
                self.spawn_terminal(str(cmd))
            elif cmd_type == 2:
                self.send_to_selected_window(str(cmd))
            elif cmd_type == 3:
                self.run_detached(str(cmd))
            elif cmd_type == "plugin":
                self.run_plugin(cmd)
            else:
                raise TVMError(f"Unknown command type: {cmd_type}")
        except Exception as exc:
            self.show_error("Command failed", f"{exc}\n\n{traceback.format_exc()}")

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
            raise TVMError(f"Plugin '{plugin_name}' was not found in {PLUGIN_DIR}.")

        run_fn = getattr(plugin, "run", None)
        if not callable(run_fn):
            raise TVMError(f"Plugin '{plugin_name}' does not define run(app, context).")

        context = {
            "window_id": self.window_id,
            "config": self.cfg,
            "plugin_dir": PLUGIN_DIR,
            "args": plugin_args,
        }
        self.log(f"Running plugin '{plugin_name}' with args={plugin_args}")
        run_fn(self, context)

    def reload_plugins_with_notice(self) -> None:
        old_names = set(self.plugins)
        old_mtimes = dict(self.plugin_mtimes)
        self.load_plugins(force=False)
        new_names = set(self.plugins)

        added = sorted(new_names - old_names)
        removed = sorted(old_names - new_names)
        changed = sorted(
            name
            for name in (new_names & old_names)
            if self.plugin_mtimes.get(name) != old_mtimes.get(name)
        )

        parts: list[str] = []
        if added:
            parts.append(f"Added: {', '.join(added)}")
        if changed:
            parts.append(f"Reloaded: {', '.join(changed)}")
        if removed:
            parts.append(f"Removed: {', '.join(removed)}")
        if not parts:
            parts.append("No plugin changes detected.")

        messagebox.showinfo("Plugins", "\n".join(parts))

    def spawn_terminal(self, cmd: str) -> None:
        self.log(f"Spawning terminal command via {self.application}: {cmd}")
        subprocess.Popen([self.application, "--", "bash", "-lc", cmd])

    def run_detached(self, cmd: str) -> None:
        self.log(f"Running detached command: {cmd}")
        subprocess.Popen(cmd, shell=True)

    def send_to_selected_window(self, cmd: str) -> None:
        if not self.window_id:
            raise TVMError("No target window selected.")

        self.log(f"Sending command to window {self.window_id}: {cmd}")
        try:
            self._run_helper(
                {
                    "action": "send",
                    "window_id": self.window_id,
                    "text": cmd,
                    "key": "Return",
                    "focus_delay_ms": 100,
                    "text_delay_us": 1200,
                    "key_delay_us": 1200,
                }
            )
        except TVMError as exc:
            logging.warning("Send failed for window %s: %s", self.window_id, exc)
            self.window_id = None
            raise TVMError(
                "Could not send command to the selected window. "
                "The target may have closed or the X11 helper failed. Re-select the window and try again."
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
        "debug = "
        + repr(default_config.debug)
        + "\n\n"
        + "terminal = "
        + repr(default_config.terminal)
        + "\n\n"
        + "Categories = "
        + repr(default_config.Categories)
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    ensure_user_config()
    cfg = load_config()
    root = Tk()
    TVMApp(root, cfg)
    root.mainloop()
    return 0
