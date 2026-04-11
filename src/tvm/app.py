from __future__ import annotations

import ast
import importlib.util
import json
import logging
import re
import subprocess
import sys
import traceback
from copy import deepcopy
from pathlib import Path
from tkinter import (
    BOTH,
    END,
    LEFT,
    RIGHT,
    Button,
    Entry,
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
CONFIG_DIR = Path.home() / ".config" / "tvm"
CONFIG_FILE = CONFIG_DIR / "config.py"
PLUGIN_DIR = CONFIG_DIR / "plugins"
LOG_FILE = CONFIG_DIR / "tvm.log"
HELPER_TIMEOUT_SECONDS = 15
COMMAND_TYPE_LABELS = {
    0: "select_window",
    1: "spawn_terminal",
    2: "send_to_window",
    3: "run_detached",
    "plugin": "plugin",
    "macro": "macro",
}
COMMAND_TYPE_VALUES = {value: key for key, value in COMMAND_TYPE_LABELS.items()}

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
        self.recording_macro = False
        self.recorded_steps: list[list[object]] = []
        self.macro_status_var = StringVar(value="Macro recorder: idle")
        self.main_frame: Frame | None = None
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

    def build_main(self) -> None:
        if self.main_frame is not None and self.main_frame.winfo_exists():
            self.main_frame.destroy()

        frame = Frame(self.root, padx=8, pady=8)
        frame.pack(fill=BOTH, expand=True)
        self.main_frame = frame

        Label(
            frame,
            text="GUI CMDs",
            bd=4,
            width=24,
            bg="lightgreen",
            fg="black",
            relief="raised",
        ).pack(pady=(0, 8))

        for category in self.cfg.Categories:
            Button(
                frame,
                text=category,
                width=24,
                bg="black",
                fg="yellow",
                command=lambda c=category: self.open_category(c),
            ).pack(pady=2)

        Button(
            frame,
            text="Reload Plugins",
            width=24,
            bg="navy",
            fg="white",
            command=self.reload_plugins_with_notice,
        ).pack(pady=(8, 2))

        Button(
            frame,
            text="Edit Buttons",
            width=24,
            bg="darkgreen",
            fg="white",
            command=self.open_button_editor,
        ).pack(pady=2)

        Button(
            frame,
            text="Macro Recorder",
            width=24,
            bg="purple",
            fg="white",
            command=self.open_macro_recorder,
        ).pack(pady=2)

        Label(frame, textvariable=self.macro_status_var, fg="blue").pack(pady=(6, 2))

        Button(
            frame,
            text="Exit",
            width=24,
            bg="red",
            fg="black",
            command=self.on_close,
        ).pack(side="bottom", pady=(10, 0))

    def refresh_ui(self) -> None:
        self.build_main()

    def open_category(self, category: str) -> None:
        win = Toplevel(self.root)
        win.title(category)
        win.protocol("WM_DELETE_WINDOW", win.destroy)

        Label(
            win,
            text=category,
            bd=4,
            width=24,
            bg="lightgreen",
            fg="black",
            relief="raised",
        ).pack(padx=8, pady=(8, 6))

        for subcategory in self.cfg.Categories[category]:
            Button(
                win,
                text=subcategory,
                width=24,
                bg="black",
                fg="yellow",
                command=lambda c=category, s=subcategory, w=win: self.select_cmd(w, c, s),
            ).pack(pady=2, padx=8)

        Button(
            win,
            text="Exit",
            width=24,
            bg="red",
            fg="black",
            command=win.destroy,
        ).pack(side="bottom", pady=(8, 8))

    def select_cmd(self, parent_window, category: str, subcategory: str) -> None:
        cmd_type, cmd = self.cfg.Categories[category][subcategory]
        if isinstance(cmd, str) and "{}" in cmd:
            self.prompt_window(cmd_type, cmd)
        else:
            self.run_cmd(cmd_type, cmd, parent_window)

    def prompt_window(self, cmd_type: int | str, cmd: str) -> None:
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
            new_cmd = cmd.replace("{}", value)
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

    def normalize_command_type(self, cmd_type) -> int | str:
        if cmd_type in COMMAND_TYPE_LABELS:
            return cmd_type
        if isinstance(cmd_type, str) and cmd_type in COMMAND_TYPE_VALUES:
            return COMMAND_TYPE_VALUES[cmd_type]
        return cmd_type

    def record_step_if_needed(self, cmd_type, cmd) -> None:
        if not self.recording_macro:
            return
        normalized = self.normalize_command_type(cmd_type)
        if normalized in (0, "macro"):
            return
        self.recorded_steps.append([normalized, deepcopy(cmd)])
        self.macro_status_var.set(f"Macro recorder: recording {len(self.recorded_steps)} step(s)")

    def run_cmd(self, cmd_type, cmd, current_window=None) -> None:
        cmd_type = self.normalize_command_type(cmd_type)
        try:
            if current_window is not None and current_window.winfo_exists():
                current_window.destroy()

            self.record_step_if_needed(cmd_type, cmd)

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
            elif cmd_type == "macro":
                self.run_macro(cmd)
            else:
                raise TVMError(f"Unknown command type: {cmd_type}")
        except Exception as exc:
            self.show_error("Command failed", f"{exc}\n\n{traceback.format_exc()}")

    def run_macro(self, cmd) -> None:
        if not isinstance(cmd, list):
            raise TVMError("Macro command must be a list of steps.")
        for index, step in enumerate(cmd, start=1):
            if not isinstance(step, (list, tuple)) or len(step) != 2:
                raise TVMError(f"Macro step {index} is invalid: {step!r}")
            step_type, step_cmd = step
            self.log(f"Running macro step {index}: type={step_type} cmd={step_cmd!r}")
            self.run_cmd(step_type, step_cmd, None)

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

    def send_text_to_window(self, text: str, press_enter: bool = True) -> None:
        if not self.window_id:
            raise TVMError("No target window selected.")

        self.log(f"Sending text to window {self.window_id}: {text}")
        key = "Return" if press_enter else ""
        try:
            self._run_helper(
                {
                    "action": "send",
                    "window_id": self.window_id,
                    "text": text,
                    "key": key,
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

    def send_to_selected_window(self, cmd: str) -> None:
        self.send_text_to_window(cmd, press_enter=True)

    def open_macro_recorder(self) -> None:
        win = Toplevel(self.root)
        win.title("Macro Recorder")
        win.protocol("WM_DELETE_WINDOW", win.destroy)

        Label(win, text="Record TVM button actions and save them as a macro button.").pack(
            padx=10, pady=(10, 6)
        )
        Label(win, textvariable=self.macro_status_var, fg="blue").pack(padx=10, pady=(0, 8))

        steps_text = Text(win, width=80, height=14)
        steps_text.pack(padx=10, pady=6)

        def refresh_steps() -> None:
            steps_text.delete("1.0", END)
            if self.recorded_steps:
                steps_text.insert("1.0", json.dumps(self.recorded_steps, indent=2))
            else:
                steps_text.insert("1.0", "[]")

        def start_recording() -> None:
            self.recorded_steps = []
            self.recording_macro = True
            self.macro_status_var.set("Macro recorder: recording 0 step(s)")
            refresh_steps()

        def stop_recording() -> None:
            self.recording_macro = False
            self.macro_status_var.set(f"Macro recorder: captured {len(self.recorded_steps)} step(s)")
            refresh_steps()

        def save_macro() -> None:
            if not self.recorded_steps:
                raise TVMError("No steps have been recorded yet.")
            category = simpledialog.askstring("Save Macro", "Category name:", parent=win)
            if not category:
                return
            label = simpledialog.askstring("Save Macro", "Button label:", parent=win)
            if not label:
                return
            self.cfg.Categories.setdefault(category, {})[label] = ["macro", deepcopy(self.recorded_steps)]
            self.save_config()
            self.refresh_ui()
            messagebox.showinfo("Macro Recorder", f"Saved macro '{label}' in category '{category}'.")

        controls = Frame(win)
        controls.pack(pady=(0, 10))
        Button(controls, text="Start", bg="darkgreen", fg="white", command=start_recording).pack(
            side=LEFT, padx=4
        )
        Button(controls, text="Stop", bg="orange", fg="black", command=stop_recording).pack(
            side=LEFT, padx=4
        )
        Button(controls, text="Save as Button", bg="navy", fg="white", command=save_macro).pack(
            side=LEFT, padx=4
        )
        Button(controls, text="Refresh View", command=refresh_steps).pack(side=LEFT, padx=4)

        refresh_steps()

    def open_button_editor(self) -> None:
        win = Toplevel(self.root)
        win.title("Button Editor")
        win.geometry("980x520")
        win.protocol("WM_DELETE_WINDOW", win.destroy)

        left = Frame(win)
        left.pack(side=LEFT, fill=BOTH, expand=False, padx=(8, 4), pady=8)
        right = Frame(win)
        right.pack(side=RIGHT, fill=BOTH, expand=True, padx=(4, 8), pady=8)

        Label(left, text="Buttons", bg="lightgreen", width=28).pack(pady=(0, 6))
        listbox = Listbox(left, width=40, height=24)
        listbox.pack(side=LEFT, fill=BOTH, expand=True)
        scroll = Scrollbar(left, orient="vertical", command=listbox.yview)
        scroll.pack(side=RIGHT, fill="y")
        listbox.config(yscrollcommand=scroll.set)

        form = Frame(right)
        form.pack(fill=BOTH, expand=True)

        category_var = StringVar()
        label_var = StringVar()
        type_var = StringVar(value="send_to_window")

        Label(form, text="Category").grid(row=0, column=0, sticky="w")
        category_entry = Entry(form, textvariable=category_var, width=32)
        category_entry.grid(row=0, column=1, sticky="ew", padx=(4, 8), pady=2)

        Label(form, text="Button Label").grid(row=1, column=0, sticky="w")
        label_entry = Entry(form, textvariable=label_var, width=32)
        label_entry.grid(row=1, column=1, sticky="ew", padx=(4, 8), pady=2)

        Label(form, text="Command Type").grid(row=2, column=0, sticky="w")
        type_entry = Entry(form, textvariable=type_var, width=32)
        type_entry.grid(row=2, column=1, sticky="ew", padx=(4, 8), pady=2)
        Label(
            form,
            text="Use: select_window, spawn_terminal, send_to_window, run_detached, plugin, macro",
            fg="gray40",
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 8))

        Label(form, text="Command / JSON Payload").grid(row=4, column=0, sticky="nw")
        cmd_text = Text(form, width=64, height=18)
        cmd_text.grid(row=4, column=1, sticky="nsew", padx=(4, 8), pady=2)
        form.grid_columnconfigure(1, weight=1)
        form.grid_rowconfigure(4, weight=1)

        index_map: list[tuple[str, str]] = []
        selected_key: dict[str, tuple[str, str] | None] = {"value": None}

        def render_cmd_value(value) -> str:
            if isinstance(value, str):
                return value
            return json.dumps(value, indent=2)

        def parse_cmd_value(raw: str):
            raw = raw.strip()
            if not raw:
                return ""
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                try:
                    return ast.literal_eval(raw)
                except Exception:
                    return raw

        def refresh_list() -> None:
            listbox.delete(0, END)
            index_map.clear()
            for category_name, buttons in self.cfg.Categories.items():
                for button_name in buttons:
                    index_map.append((category_name, button_name))
                    listbox.insert(END, f"{category_name} / {button_name}")

        def load_selected(_event=None) -> None:
            selection = listbox.curselection()
            if not selection:
                return
            category_name, button_name = index_map[selection[0]]
            selected_key["value"] = (category_name, button_name)
            cmd_type, cmd = self.cfg.Categories[category_name][button_name]
            category_var.set(category_name)
            label_var.set(button_name)
            type_var.set(COMMAND_TYPE_LABELS.get(cmd_type, str(cmd_type)))
            cmd_text.delete("1.0", END)
            cmd_text.insert("1.0", render_cmd_value(cmd))

        def clear_form() -> None:
            selected_key["value"] = None
            category_var.set("")
            label_var.set("")
            type_var.set("send_to_window")
            cmd_text.delete("1.0", END)

        def save_entry() -> None:
            category_name = category_var.get().strip()
            button_name = label_var.get().strip()
            if not category_name or not button_name:
                raise TVMError("Category and button label are required.")

            raw_type = type_var.get().strip()
            cmd_type = COMMAND_TYPE_VALUES.get(raw_type, raw_type)
            if cmd_type not in COMMAND_TYPE_LABELS:
                raise TVMError(f"Unsupported command type: {raw_type}")

            cmd_value = parse_cmd_value(cmd_text.get("1.0", END))
            old_key = selected_key["value"]
            if old_key and old_key != (category_name, button_name):
                old_category, old_button = old_key
                if old_category in self.cfg.Categories:
                    self.cfg.Categories[old_category].pop(old_button, None)
                    if not self.cfg.Categories[old_category]:
                        self.cfg.Categories.pop(old_category, None)

            self.cfg.Categories.setdefault(category_name, {})[button_name] = [cmd_type, cmd_value]
            self.save_config()
            self.refresh_ui()
            refresh_list()
            selected_key["value"] = (category_name, button_name)
            messagebox.showinfo("Button Editor", "Button saved.")

        def delete_entry() -> None:
            key = selected_key["value"]
            if not key:
                raise TVMError("Select a button to delete.")
            category_name, button_name = key
            if not messagebox.askyesno("Delete Button", f"Delete '{button_name}' from '{category_name}'?"):
                return
            self.cfg.Categories.get(category_name, {}).pop(button_name, None)
            if category_name in self.cfg.Categories and not self.cfg.Categories[category_name]:
                self.cfg.Categories.pop(category_name, None)
            self.save_config()
            self.refresh_ui()
            refresh_list()
            clear_form()

        def add_category() -> None:
            name = simpledialog.askstring("New Category", "Category name:", parent=win)
            if not name:
                return
            self.cfg.Categories.setdefault(name.strip(), {})
            self.save_config()
            self.refresh_ui()
            refresh_list()

        buttons = Frame(right)
        buttons.pack(fill="x", pady=(8, 0))
        Button(buttons, text="New", command=clear_form, bg="gray20", fg="white").pack(side=LEFT, padx=4)
        Button(buttons, text="Save", command=lambda: self._guarded_editor_action(save_entry), bg="darkgreen", fg="white").pack(side=LEFT, padx=4)
        Button(buttons, text="Delete", command=lambda: self._guarded_editor_action(delete_entry), bg="darkred", fg="white").pack(side=LEFT, padx=4)
        Button(buttons, text="Add Category", command=add_category, bg="navy", fg="white").pack(side=LEFT, padx=4)
        Button(buttons, text="Close", command=win.destroy).pack(side=LEFT, padx=4)

        listbox.bind("<<ListboxSelect>>", load_selected)
        refresh_list()

    def _guarded_editor_action(self, func) -> None:
        try:
            func()
        except Exception as exc:
            self.show_error("Editor Error", f"{exc}\n\n{traceback.format_exc()}")

    def save_config(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        text = (
            "debug = "
            + repr(getattr(self.cfg, "debug", {}))
            + "\n\n"
            + "terminal = "
            + repr(getattr(self.cfg, "terminal", {}))
            + "\n\n"
            + "Categories = "
            + repr(self.cfg.Categories)
            + "\n"
        )
        CONFIG_FILE.write_text(text, encoding="utf-8")
        self.log(f"Saved config to {CONFIG_FILE}")

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
