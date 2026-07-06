from __future__ import annotations
from .backends.base import BackendError
from .backends.x11_backend import X11Backend
from .backends.tmux_backend import TmuxBackend
from .backends.subprocess_backend import SubprocessBackend

from .ui.backend_output import BackendOutputViewerWindow
from .ui.backend_manager import BackendManagerWindow
from .ui.shared_variables import SharedVariableManagerWindow
from .ui.workflow_picker import WorkflowPickerWindow
from .ui.workflow_monitor import (
    WorkflowLiveMonitorWindow,
    WorkflowHistoryViewerWindow,
)
from .ui.workflow_visualizer import WorkflowVisualizerWindow
from .ui.workflow_variables import WorkflowVariablesWindow
from .ui.schedules import (
    ScheduleManagerWindow,
    ScheduleHistoryWindow,
)
from .ui.workflow_editor import WorkflowEditorWindow
from .ui.category_editor import (
    CategoryEditorWindow,
    CommandEditorWindow,
)
from .ui.chain_builder import (
    ChainBuilderWindow,
    ChainRunnerWindow,
)
from .ui.workflow_manager import WorkflowManagerWindow
from .ui.variables import (
    VariableManagerWindow,
    EnvironmentTemplateWindow,
)
from .ui.tools import (
    PluginManagerWindow,
    TagManagerWindow,
    ExecutionQueueWindow,
)
from .ui.launcher import (
    HotkeyEditorWindow,
    CommandPaletteWindow,
)
from .ui.dialogs import MultiFieldPrompt
from .ui.backups import BackupManagerWindow
from .ui.profiles import (
    ProfileManagerWindow,
    ConfigHealthCheckWindow,
)
from .ui.settings import SettingsWindow
from .ui.theme import button_style
from .utils.parsing import (
    parse_command_entry,
)
from .utils.workflows import (
    clean_captured_output,
    extract_termforge_capture,
)
from .utils.variables import (
    resolve_shared_variables,
    resolve_workflow_variables,
)
from .utils.variables import (
    resolve_shared_variables,
    resolve_workflow_variables,
)
from .utils.validation import validate_workflow_steps
from .services.backup_service import create_project_snapshot
from .services.workflow_service import (
    start_workflow_state as make_workflow_state,
    update_workflow_step_state as update_workflow_step,
    finish_workflow_state as finish_workflow,
)
from .services.variable_service import (
    get_shared_variables as svc_get_shared_variables,
    set_shared_variable as svc_set_shared_variable,
    delete_shared_variable as svc_delete_shared_variable,
)
from .errors import TermForgeError
from .constants import CONFIG_DIR

import tarfile
import importlib.util
import json
import logging
import pprint
import re
import os
import subprocess
import sys
import time
import copy
import traceback
import shutil
import html
import webbrowser
import shlex
import socket
from datetime import datetime
from pathlib import Path

try:
    from pynput import keyboard as pynput_keyboard
except Exception:
    pynput_keyboard = None
from tkinter import (
    BOTH,
    END,
    LEFT,
    RIGHT,
    X,
    Y,
    Button,
    Checkbutton,
    Entry,
    Frame,
    IntVar,
    Label,
    Listbox,
    Menu,
    OptionMenu,
    Scrollbar,
    StringVar,
    Text,
    Tk,
    ttk,
    Toplevel,
    filedialog,
    messagebox,
    PanedWindow,
    simpledialog,
)
from .constants import (
    APP_NAME,
    APP_VERSION,
    APP_SLUG,
    PLUGIN_API_VERSION,
    MAX_HISTORY,
    CONFIG_DIR,
    CONFIG_FILE,
    STATE_FILE,
    LOG_FILE,
    PLACEHOLDER_RE,
    HELPER_TIMEOUT_SECONDS,
    PLUGIN_DIR,
    BACKUP_DIR,
    PROJECT_BACKUP_DIR,
    PRIORITY_ORDER,
    DEFAULT_BACKEND,
    DEFAULT_TMUX_SESSION,
    DEFAULT_TMUX_MODE,
)

CONFIG_DIR.mkdir(parents=True, exist_ok=True)
PLUGIN_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

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

    "TmuxMode = 'pane'",
    "TmuxSession = 'termforge'",
    "TmuxPane = ''",

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
        "Tags = {}",
        "Schedules = []",
        "ScheduleHistory = []",
        "SchedulerPaused = False",
        "BackupDir = str(CONFIG_DIR / 'backups')",
        "ExecutionHistory = []",
        "Variables = {}",
        "EnvironmentTemplates = {}",
        "Workflows = {}",
        "Backend = x11",
        f"TmuxSession = {repr(tmux_session)}",
        f"TmuxPane = {repr(tmux_pane)}",
        "SharedVariables = {}",
        "",
    ]
    backup_dir = Path(getattr(cfg, "BackupDir", CONFIG_DIR / "backups"))
    backup_dir.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text("\n".join(lines), encoding="utf-8")


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
        self.set_status("Scheduler: PAUSED" if self.is_scheduler_paused() else "Scheduler: ACTIVE")
        self._last_backup_time = 0
        self.execution_queue = []
        self.execution_running = False
        self.execution_queue_paused = False
        self.current_job = None
        self.current_job_started_at = None
        self.completed_jobs = []
        self.current_process = None
        self.current_process_job = None
        self.current_environment = None
        self.current_workflow_state = None
        self.workflow_history = []
        self.workflow_output_vars = {}
        self.variable_prompt_cache = {}

        self.backend = self.create_backend()

        try:
            report = self.backend_health_report()
            if report.get("warning") and self.get_backend_name() != report.get("recommended_backend"):
                self.log(f"Backend warning: {report.get('warning')}")
        except Exception:
            pass

        if self.debug:
            logging.getLogger().setLevel(logging.DEBUG)

        self.load_state()
        self.log("Starting TermForge")
        self.load_plugins(force=True)
        self.build_main()
        self.start_scheduler()
        self.bind_global_shortcuts()
        self.initialize_hotkeys()
        self.root.after(250, self.safe_initial_select)

    def show_toast(self, message: str, duration_ms: int = 4000) -> None:
        win = Toplevel(self.root)
        win.overrideredirect(True)

        width = 360
        height = 120

        try:
            screen_w = win.winfo_screenwidth()
            screen_h = win.winfo_screenheight()
        except Exception:
            screen_w = 1920
            screen_h = 1080

        x = screen_w - width - 24
        y = screen_h - height - 64

        win.geometry(f"{width}x{height}+{x}+{y}")

        outer = Frame(
            win,
            bg="#222222",
            bd=2,
            relief="raised",
            padx=10,
            pady=10,
        )
        outer.pack(fill=BOTH, expand=True)

        Label(
            outer,
            text="TermForge Notification",
            bg="#444444",
            fg="white",
            relief="raised",
            bd=2,
        ).pack(fill=X, pady=(0, 8))

        Label(
            outer,
            text=message,
            bg="#222222",
            fg="white",
            justify=LEFT,
            wraplength=320,
        ).pack(fill=BOTH, expand=True)

        win.after(duration_ms, win.destroy)

    def show_traceback_window(self, title: str, exc) -> None:
        tb = traceback.format_exc()
        if tb.strip() == "NoneType: None":
            tb = str(exc)

        win = Toplevel(self.root)
        win.title(title)
        win.geometry("1000x700")

        outer = Frame(win, padx=8, pady=8)
        outer.pack(fill=BOTH, expand=True)

        Label(
            outer,
            text=title,
            bg="#aa3333",
            fg="white",
            relief="raised",
            bd=4,
            width=40,
        ).pack(fill=X, pady=(0, 8))

        text = Text(outer, wrap="none")
        text.pack(fill=BOTH, expand=True)

        yscroll = Scrollbar(text, orient="vertical", command=text.yview)
        xscroll = Scrollbar(text, orient="horizontal", command=text.xview)

        text.configure(
            yscrollcommand=yscroll.set,
            xscrollcommand=xscroll.set,
        )

        yscroll.pack(side=RIGHT, fill=Y)
        xscroll.pack(side="bottom", fill=X)

        text.insert(
            "1.0",
            f"{type(exc).__name__}: {exc}\n\n{tb}"
        )

        button_row = Frame(outer)
        button_row.pack(fill=X, pady=(8, 0))

        def copy_all():
            win.clipboard_clear()
            win.clipboard_append(text.get("1.0", END))
            win.update()

        Button(
            button_row,
            text="Copy Traceback",
            width=18,
            bg="#2f5597",
            fg="white",
            command=copy_all,
        ).pack(side=LEFT)

        Button(
            button_row,
            text="Close",
            width=14,
            bg="red",
            fg="black",
            command=win.destroy,
        ).pack(side=RIGHT)

    def log(self, message: str) -> None:
        # Internal app logger.
        # Intentionally silent unless debug mode is enabled.
        try:
            debug_enabled = getattr(self.cfg, "debug", {}).get("Flag", False)
        except Exception:
            debug_enabled = False

        if debug_enabled:
            try:
                print(f"[TermForge] {message}")
            except Exception:
                pass

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
            raw = STATE_FILE.read_text(encoding="utf-8").strip()

            if not raw:
                return {}

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                bad = STATE_FILE.with_suffix(".bad.json")
                STATE_FILE.replace(bad)
                return {}
            self.last_window_id = data.get("last_window_id")
            history = data.get("command_history", [])
            if isinstance(history, list):
                self.command_history = history[:MAX_HISTORY]
        except Exception as exc:
            self.show_traceback_window("Could not load state file: ", exc)

    def save_state(self) -> None:
        try:
            payload = {
                "last_window_id": self.window_id if self.window_id is not None else self.last_window_id,
                "command_history": self.command_history[:MAX_HISTORY],
            }
            STATE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as exc:
            self.show_traceback_window("Could not save state file: ", str(exc))

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

    def get_builtin_variables(self) -> dict:
        now = datetime.now()

        return {
            "HOME": os.path.expanduser("~"),
            "PWD": os.getcwd(),
            "USER": os.environ.get("USER", ""),
            "HOSTNAME": socket.gethostname(),
            "DATE": now.strftime("%Y-%m-%d"),
            "TIME": now.strftime("%H:%M:%S"),
            "TIMESTAMP": now.strftime("%Y-%m-%d_%H-%M-%S"),
        }


    def get_all_variables(self) -> dict:
        data = {}

        builtins = self.get_builtin_variables()
        shared = getattr(self.cfg, "SharedVariables", {})
        workflow = getattr(self, "workflow_output_vars", {})

        if isinstance(builtins, dict):
            data.update(builtins)

        if isinstance(shared, dict):
            data.update(shared)

        if isinstance(workflow, dict):
            data.update(workflow)

        return data


    def resolve_variable_value(self, value: str, seen: set | None = None) -> str:
        if seen is None:
            seen = set()

        variables = self.get_all_variables()

        def replace(match):
            name = match.group(1).strip()

            if name.startswith("prompt:"):
                prompt_label = name.split(":", 1)[1].strip() or "Enter value"

                cache_key = f"prompt:{prompt_label}"

                if cache_key in self.variable_prompt_cache:
                    return self.variable_prompt_cache[cache_key]

                value = simpledialog.askstring(
                    "TermForge Variable Prompt",
                    prompt_label,
                    parent=getattr(self, "root", None),
                )

                if value is None:
                    raise TermForgeError(f"Prompt cancelled: {prompt_label}")

                self.variable_prompt_cache[cache_key] = value
                return value

            if name in seen:
                raise TermForgeError(
                    "Circular variable reference: "
                    + " -> ".join(list(seen) + [name])
                )

            if name not in variables:
                return match.group(0)

            seen.add(name)
            resolved = self.resolve_variable_value(str(variables[name]), seen)
            seen.remove(name)

            return resolved

        return re.sub(r"\$\{([^}]+)\}", replace, str(value))


    def resolve_text_variables(self, text: str) -> str:
        return self.resolve_variable_value(str(text))

    def open_settings(self):
        SettingsWindow(self)

    def open_workflow_picker(self):
        WorkflowPickerWindow(self)

    def open_workflow_variables(self):
        WorkflowVariablesWindow(self)

    def open_backend_output_viewer(self):
        BackendOutputViewerWindow(self)

    def open_workflow_editor(self, workflow_name: str | None = None):

        workflows = self.get_workflows()

        if workflow_name is None:
            names = sorted(workflows.keys())

            if not names:
                self.show_traceback_window(
                    "Workflow Editor",
                    Exception("No workflows exist yet."),
                )
                return

            workflow_name = names[0]

        WorkflowEditorWindow(self, workflow_name)

    def record_backend_output(self, output: dict) -> None:
        if not hasattr(self, "backend_outputs"):
            self.backend_outputs = []

        self.backend_outputs.insert(0, output)
        del self.backend_outputs[100:]

    def open_shared_variable_manager(self):
        SharedVariableManagerWindow(self)

    def open_workflow_manager(self):
        WorkflowManagerWindow(self)

    def open_workflow_history_viewer(self):
        WorkflowHistoryViewerWindow(self)

    def open_workflow_live_monitor(self):
        WorkflowLiveMonitorWindow(self)

    def open_terminal_output_viewer(self):
        TerminalOutputViewerWindow(self)

    def open_backend_manager(self):
        BackendManagerWindow(self)

    def open_environment_templates(self):
        EnvironmentTemplateWindow(self)

    def open_variable_manager(self) -> None:
        VariableManagerWindow(self)

    def open_config_health_check(self) -> None:
        ConfigHealthCheckWindow(self)

    def open_profile_manager(self) -> None:
        ProfileManagerWindow(self)

    def open_profiles(self) -> dict:
        ProfileManagerWindow(self)

    def open_execution_queue(self) -> None:
        ExecutionQueueWindow(self)

    def open_tag_manager(self) -> None:
        TagManagerWindow(self)

    def open_schedule_manager(self) -> None:
        ScheduleManagerWindow(self)

    def open_schedule_history(self) -> None:
        ScheduleHistoryWindow(self)

    def open_hotkey_editor(self) -> None:
        HotkeyEditorWindow(self)

    def open_plugin_manager(self) -> None:
        PluginManagerWindow(self)

    def open_command_editor(self) -> None:
        CommandEditorWindow(self)

    def open_category_editor(self) -> None:
        CategoryEditorWindow(self)

    def open_command_palette(self, event=None) -> None:
        CommandPaletteWindow(self)
        return "break"

    def open_backup_manager(self) -> None:
        BackupManagerWindow(self)

    def get_project_root(self) -> Path:
        # app.py is usually src/termforge/app.py
        return Path(__file__).resolve().parents[2]

    def create_project_snapshot_backup(self) -> Path:
        target = create_project_snapshot(self.get_project_root())
        self.set_status(f"Project snapshot created: {target}")
        return target

    def get_shared_variables(self) -> dict:
        return svc_get_shared_variables(self.cfg)

    def set_shared_variable(self, name: str, value: str) -> None:
        svc_set_shared_variable(self.cfg, name, value)
        self.persist_full_config()

    def delete_shared_variable(self, name: str) -> None:
        svc_delete_shared_variable(self.cfg, name)
        self.persist_full_config()

    def resolve_shared_variables_in_text(self, text: str) -> str:
        return resolve_shared_variables(
            text,
            self.get_shared_variables(),
        )

    def clean_captured_output(self, text: str) -> str:
        return clean_captured_output(text)

    def extract_termforge_capture(self, output: str) -> str:
        return extract_termforge_capture(output)

    def get_workflow_output_vars(self) -> dict:
        if not self.current_workflow_state:
            return {}

        return self.current_workflow_state.setdefault("output_vars", {})

    def set_workflow_output_var(self, name: str, value: str) -> None:
        name = str(name).strip()

        if not name:
            return

        output_vars = self.get_workflow_output_vars()
        output_vars[name] = value

    def resolve_workflow_output_vars(self, text: str) -> str:
        return self.resolve_text_variables(text)

    def snapshot_backend_context(self) -> dict:
        return {
            "backend": getattr(self.cfg, "Backend", "x11"),
            "tmux_session": getattr(self.cfg, "TmuxSession", "termforge"),
            "tmux_pane": getattr(self.cfg, "TmuxPane", ""),
            "tmux_mode": getattr(self.cfg, "TmuxMode", "pane"),
            "current_environment": self.get_current_environment(),
        }

    def restore_backend_context(self, ctx: dict) -> None:
        setattr(self.cfg, "Backend", ctx.get("backend", "x11"))
        setattr(self.cfg, "TmuxSession", ctx.get("tmux_session", "termforge"))
        setattr(self.cfg, "TmuxPane", ctx.get("tmux_pane", ""))
        setattr(self.cfg, "TmuxMode", ctx.get("tmux_mode", "pane"))

        self.current_environment = ctx.get("current_environment")
        self.backend = self.create_backend()


    def apply_backend_override(self, data: dict) -> None:
        backend_name = str(data.get("backend", "")).strip().lower()

        if not backend_name:
            return

        if backend_name not in ("x11", "subprocess", "tmux"):
            raise TermForgeError(f"Unknown backend override: {backend_name}")

        setattr(self.cfg, "Backend", backend_name)

        if backend_name == "tmux":
            setattr(
                self.cfg,
                "TmuxSession",
                data.get("tmux_session", getattr(self.cfg, "TmuxSession", "termforge")),
            )
            setattr(
                self.cfg,
                "TmuxPane",
                data.get("tmux_pane", getattr(self.cfg, "TmuxPane", "")),
            )
            setattr(
                self.cfg,
                "TmuxMode",
                data.get("tmux_mode", getattr(self.cfg, "TmuxMode", "pane")),
            )

        self.backend = self.create_backend()

    def capture_backend_output(self, lines: int = 120) -> str:
        try:
            backend = getattr(self, "backend", None)

            if isinstance(backend, TmuxBackend):
                return self.clean_captured_output(
                    backend.capture_output(lines=lines)
                )

            return ""
        except Exception as exc:
            return f"[capture failed: {exc}]"

    def start_workflow_state(self, name: str, total: int, mode: str = "sequential"):
        self.current_workflow_state = {
            "name": name,
            "mode": mode,
            "total": total,
            "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "finished_at": "",
            "status": "running",
            "steps": {},
            "output_vars": {},
        }

    def update_workflow_step_state(
        self,
        step_id: str,
        status: str,
        message: str = "",
        output: str = "",
    ):
        if not self.current_workflow_state:
            return

        steps = self.current_workflow_state.setdefault("steps", {})

        row = steps.setdefault(
            step_id,
            {
                "id": step_id,
                "status": "",
                "started_at": "",
                "finished_at": "",
                "message": "",
                "output": "",
            },
        )

        row["status"] = status
        row["message"] = message
        if output:
            row["output"] = output

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if status == "running" and not row.get("started_at"):
            row["started_at"] = now

        if status in ("success", "failed", "skipped"):
            row["finished_at"] = now

    def finish_workflow_state(self, status: str = "finished"):
        state = finish_workflow(
            self.current_workflow_state,
            status,
        )

        if state:
            state["variables"] = dict(getattr(self, "workflow_output_vars", {}))
            self.workflow_history.insert(0, dict(state))
            del self.workflow_history[50:]

    def detect_session_type(self) -> str:
        session = os.environ.get("XDG_SESSION_TYPE", "").strip().lower()

        if session:
            return session

        if os.environ.get("WAYLAND_DISPLAY"):
            return "wayland"

        if os.environ.get("DISPLAY"):
            return "x11"

        return "unknown"


    def backend_health_report(self) -> dict:
        session = self.detect_session_type()
        current = self.get_backend_name()

        xdotool_available = shutil.which("xdotool") is not None
        display = os.environ.get("DISPLAY", "")
        wayland_display = os.environ.get("WAYLAND_DISPLAY", "")
        tmux_available = shutil.which("tmux") is not None

        if session == "wayland":
            recommended = "tmux" if tmux_available else "subprocess"
            warning = (
                "Wayland detected. X11 backend may only work with XWayland windows. "
                "Subprocess backend is recommended for cross-desktop compatibility."
            )
        elif session == "x11":
            recommended = "x11" if xdotool_available else ("tmux" if tmux_available else "subprocess")
            warning = "" if xdotool_available else "xdotool not found; subprocess is recommended."
        else:
            recommended = "tmux" if tmux_available else "subprocess"
            warning = "Could not detect graphical session; subprocess is safest."

        return {
            "session": session,
            "current_backend": current,
            "recommended_backend": recommended,
            "xdotool_available": xdotool_available,
            "DISPLAY": display,
            "WAYLAND_DISPLAY": wayland_display,
            "warning": warning,
            "tmux_available": tmux_available,
        }


    def auto_select_backend(self) -> None:
        report = self.backend_health_report()
        recommended = report.get("recommended_backend", "subprocess")

        self.set_backend_name(recommended)

    def get_backend_name(self) -> str:
        return str(getattr(self.cfg, "Backend", "x11") or "x11")


        if name not in ("x11", "subprocess", "tmux"):
            name = str(name).strip().lower()

            if name not in ("x11", "subprocess"):
                raise TermForgeError(f"Unknown backend: {name}")

            setattr(self.cfg, "Backend", name)
            self.backend = self.create_backend()
            self.persist_full_config()

            self.set_status(f"Backend selected: {name}")


    def set_backend_name(self, name: str) -> None:
        name = str(name).strip().lower()

        if name not in ("x11", "subprocess", "tmux"):
            raise TermForgeError(f"Unknown backend: {name}")

        setattr(self.cfg, "Backend", name)

        selected = self.get_selected_window_id()

        if selected:
            setattr(self.backend, "selected_window_id", selected)

        self.backend = self.create_backend()

        self.persist_full_config()
        self.set_status(f"Backend selected: {name}")

    def create_backend(self):
        name = self.get_backend_name()

        if name == "subprocess":
            return SubprocessBackend(self)

        if name == "tmux":
            return TmuxBackend(self)

        return X11Backend(self)


    def workflow_step_can_run(self, step: dict, completed: set, failed: set) -> bool:
        depends_on = step.get("depends_on", [])

        if isinstance(depends_on, str):
            depends_on = [depends_on]

        run_if = str(step.get("run_if", "always")).strip().lower() or "always"

        missing = [
            dep for dep in depends_on
            if dep not in completed and dep not in failed
        ]

        if missing:
            return False

        dep_failed = any(dep in failed for dep in depends_on)

        if run_if == "never":
            return False

        if run_if == "success" and dep_failed:
            return False

        if run_if == "failed" and not dep_failed:
            return False

        return True

    def run_workflow_step(self, workflow_name: str, step: dict) -> tuple[str, bool, str, str]:
        step_id = str(step.get("id", "")).strip()
        backend_ctx = self.snapshot_backend_context()

        backend_name = str(step.get("backend", "")).strip().lower()
        is_subprocess_step = backend_name == "subprocess"

        after_output = ""

        try:
            self.apply_backend_override(step)

            before_output = ""
            if not is_subprocess_step:
                before_output = self.capture_backend_output(lines=80)

            environment = step.get("environment", "")
            profile = step.get("profile", "")
            command = step.get("command")
            capture_variable = str(step.get("capture_variable", "")).strip()

            if environment:
                self.set_current_environment(str(environment))

            if profile:
                self.select_window_profile(str(profile))

            if isinstance(command, str):
                command = self.resolve_workflow_output_vars(command)

                if "/" not in command:
                    raise TermForgeError(
                        f"Workflow command string must be Category/Command: {command}"
                    )

                category, cmd_name = command.split("/", 1)
                self.select_cmd(None, category, cmd_name)

            elif isinstance(command, (list, tuple)):
                cmd_type, cmd_text, options = parse_command_entry(command)

                cmd_text = self.resolve_text_variables(str(cmd_text))

                if isinstance(cmd_text, str):
                    cmd_text = self.resolve_workflow_output_vars(cmd_text)

                if is_subprocess_step:
                    backend = self.backend

                    if not hasattr(backend, "run_capture"):
                        backend = SubprocessBackend(self)

                    captured = backend.run_capture(str(cmd_text))

                    output_text = (
                        f"STDOUT:\n{captured.get('stdout', '')}\n\n"
                        f"STDERR:\n{captured.get('stderr', '')}\n\n"
                        f"RETURN CODE: {captured.get('returncode')}"
                    )

                    if captured.get("returncode") != 0:
                        return (
                            step_id,
                            False,
                            f"Subprocess command failed with return code {captured.get('returncode')}",
                            output_text,
                        )

                    if capture_variable:
                        captured_value = captured.get("stdout", "").strip()
                        self.set_workflow_output_var(capture_variable, captured_value)

                    return step_id, True, "", output_text

                self.run_cmd(
                    cmd_type,
                    cmd_text,
                    options,
                    None,
                    record_history=False,
                )

            else:
                raise TermForgeError(
                    f"Invalid workflow command for step {step_id}: {command!r}"
                )

            if not is_subprocess_step:
                after_output = self.capture_backend_output(lines=120)

            if capture_variable:
                captured_value = (
                    after_output.strip().splitlines()[-1]
                    if after_output.strip()
                    else ""
                )
                self.set_workflow_output_var(capture_variable, captured_value)

                self.log(
                    f"Workflow captured variable: "
                    f"{capture_variable}={captured_value!r}"
                )

            return step_id, True, "", after_output

        except Exception as exc:
            if is_subprocess_step:
                after_output = str(exc)
            else:
                try:
                    after_output = self.capture_backend_output(lines=120)
                except Exception:
                    after_output = str(exc)

            return step_id, False, str(exc), after_output

        finally:
            self.restore_backend_context(backend_ctx)

    def run_workflow_parallel(
        self,
        name: str,
        source: str = "workflow-parallel",
    ) -> None:
        workflows = self.get_workflows()
        steps = workflows.get(name)

        if steps is None:
            raise TermForgeError(f"Unknown workflow: {name}")

        errors = self.validate_workflow(steps)
        if errors:
            raise TermForgeError(
                "Workflow validation failed:\n" + "\n".join(errors)
            )

        step_map = {
            str(step.get("id", "")).strip(): step
            for step in steps
            if isinstance(step, dict) and str(step.get("id", "")).strip()
        }

        completed = set()
        failed = set()
        skipped = set()

        total = len(step_map)

        self.start_workflow_state(
            name,
            total,
            mode="dependency-wave",
        )

        runner = self.get_chain_runner(total)
        runner.log("──", f"Dependency workflow started — {name}")

        max_iterations = max(total * 3, 3)
        iterations = 0

        while len(completed) + len(failed) + len(skipped) < total:
            iterations += 1

            if iterations > max_iterations:
                message = "Workflow stopped: dependency loop safety limit reached."
                runner.step_failed(message)

                for step_id in step_map:
                    if (
                        step_id not in completed
                        and step_id not in failed
                        and step_id not in skipped
                    ):
                        skipped.add(step_id)
                        self.update_workflow_step_state(
                            step_id,
                            "skipped",
                            message,
                        )

                break

            ready = []

            for step_id, step in step_map.items():
                if (
                    step_id in completed
                    or step_id in failed
                    or step_id in skipped
                ):
                    continue

                depends_on = step.get("depends_on", [])

                if isinstance(depends_on, str):
                    depends_on = [depends_on]

                missing = [
                    dep for dep in depends_on
                    if dep not in completed and dep not in failed
                ]

                if missing:
                    continue

                run_if = (
                    str(step.get("run_if", "always"))
                    .strip()
                    .lower()
                    or "always"
                )

                dep_failed = any(dep in failed for dep in depends_on)

                if run_if == "never":
                    skipped.add(step_id)
                    runner.step_done(f"Skipped by run_if=never: {step_id}")

                    self.update_workflow_step_state(
                        step_id,
                        "skipped",
                        "Skipped by run_if=never",
                    )
                    continue

                if run_if == "success" and dep_failed:
                    skipped.add(step_id)
                    runner.step_done(
                        f"Skipped because dependency failed: {step_id}"
                    )

                    self.update_workflow_step_state(
                        step_id,
                        "skipped",
                        "Skipped because dependency failed",
                    )
                    continue

                if run_if == "failed" and not dep_failed:
                    skipped.add(step_id)
                    runner.step_done(
                        f"Skipped because no dependency failed: {step_id}"
                    )

                    self.update_workflow_step_state(
                        step_id,
                        "skipped",
                        "Skipped because no dependency failed",
                    )
                    continue

                ready.append((step_id, step))

            if not ready:
                unresolved = [
                    step_id
                    for step_id in step_map
                    if step_id not in completed
                    and step_id not in failed
                    and step_id not in skipped
                ]

                for step_id in unresolved:
                    skipped.add(step_id)
                    message = f"Skipped unresolved workflow step: {step_id}"
                    runner.step_failed(message)

                    self.update_workflow_step_state(
                        step_id,
                        "skipped",
                        message,
                    )

                break

            results = []

            for step_id, step in ready:
                self.update_workflow_step_state(
                    step_id,
                    "running",
                    "Running dependency-wave step",
                )

                runner.step_running(
                    len(completed) + len(failed) + len(skipped) + 1,
                    total,
                    f"dependency wave step {step_id}",
                )

                result = self.run_workflow_step(name, step)
                results.append(result)

            for step_id, ok, error, output in results:
                if ok:
                    completed.add(step_id)

                    runner.step_done(f"Workflow step complete: {step_id}")

                    self.update_workflow_step_state(
                        step_id,
                        "success",
                        "Step completed",
                        output=output,
                    )
                else:
                    failed.add(step_id)

                    runner.step_failed(
                        f"Workflow step failed: {step_id}: {error}"
                    )

                    self.update_workflow_step_state(
                        step_id,
                        "failed",
                        error,
                        output=output,
                    )

        self.add_history_entry(
            "workflow_dependency",
            f"{name}: {len(completed)}/{total} completed, "
            f"{len(failed)} failed, {len(skipped)} skipped",
            source=source,
        )

        self.set_status(
            f"Workflow {name}: "
            f"{len(completed)}/{total} completed, "
            f"{len(failed)} failed, "
            f"{len(skipped)} skipped."
        )

        final_status = "failed" if failed else "finished"
        self.finish_workflow_state(final_status)

        runner.finished()

    def enqueue_workflow(
        self,
        workflow_name: str,
        source: str = "workflow",
        priority: str = "normal",
    ) -> None:
        workflow_name = workflow_name.strip()

        if workflow_name not in self.get_workflows():
            raise TermForgeError(f"Unknown workflow: {workflow_name}")

        if priority not in PRIORITY_ORDER:
            priority = "normal"

        job = {
            "kind": "workflow",
            "workflow": workflow_name,
            "category": "workflow",
            "command": workflow_name,
            "source": source,
            "priority": priority,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        self.execution_queue.append(job)
        self.add_execution_history(job, "queued", "")

        self.set_status(
            f"Queued workflow {workflow_name} "
            f"({len(self.execution_queue)} pending)"
        )

        self.root.after(10, self.process_execution_queue)

    def get_workflows(self) -> dict:
        workflows = getattr(self.cfg, "Workflows", None)
        if workflows is None or not isinstance(workflows, dict):
            workflows = {}
            setattr(self.cfg, "Workflows", workflows)
        return workflows


    def set_workflow(self, name: str, steps: list) -> None:
        name = name.strip()
        if not name:
            raise TermForgeError("Workflow name is required.")

        if not isinstance(steps, list):
            raise TermForgeError("Workflow steps must be a list.")

        workflows = self.get_workflows()
        workflows[name] = steps
        setattr(self.cfg, "Workflows", workflows)
        self.persist_full_config()


    def delete_workflow(self, name: str) -> None:
        workflows = self.get_workflows()
        workflows.pop(name, None)
        setattr(self.cfg, "Workflows", workflows)
        self.persist_full_config()

    def validate_workflow(self, steps):
        return validate_workflow_steps(steps)

    def run_workflow(
        self,
        name: str,
        source: str = "workflow",
        start_at: str | None = None,
    ) -> None:
        self.variable_prompt_cache = {}
        workflows = self.get_workflows()
        steps = workflows.get(name)

        if steps is None:
            raise TermForgeError(f"Unknown workflow: {name}")

        errors = self.validate_workflow(steps)
        if errors:
            raise TermForgeError(
                "Workflow validation failed:\n" + "\n".join(errors)
            )

        completed = set()
        failed = set()
        skipped = set()
        results = {}

        total = len(steps)

        self.start_workflow_state(
            name,
            total,
            mode="sequential",
        )

        start_found = start_at is None

        runner = self.get_chain_runner(total)
        runner.log("──", f"Workflow started — {name}")

        for index, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                message = f"Invalid workflow step: {step!r}"
                step_id = f"step-{index}"

                runner.step_failed(message)
                failed.add(step_id)
                results[step_id] = False

                self.update_workflow_step_state(
                    step_id,
                    "failed",
                    message,
                )
                continue

            step_id = str(step.get("id", f"step-{index}")).strip()

            if not start_found:
                if step_id == start_at:
                    start_found = True
                else:
                    skipped.add(step_id)
                    completed.add(step_id)
                    results[step_id] = None

                    runner.step_done(
                        f"Skipped before retry start: {step_id}"
                    )
                    self.update_workflow_step_state(
                        step_id,
                        "skipped",
                        "Skipped before retry start",
                    )
                    continue

            depends_on = step.get("depends_on", [])

            if isinstance(depends_on, str):
                depends_on = [depends_on]

            run_if = (
                str(step.get("run_if", "success"))
                .strip()
                .lower()
                or "success"
            )

            missing = [
                dep for dep in depends_on
                if dep not in results
            ]

            if missing:
                message = (
                    f"Skipped {step_id}; unknown/unmet dependencies: "
                    f"{missing}"
                )

                runner.step_failed(message)

                failed.add(step_id)
                results[step_id] = False

                self.update_workflow_step_state(
                    step_id,
                    "failed",
                    message,
                )
                continue

            dep_failed = any(results.get(dep) is False for dep in depends_on)
            dep_success = all(results.get(dep) is True for dep in depends_on)

            if run_if == "never":
                runner.step_done(f"Skipped by run_if=never: {step_id}")

                skipped.add(step_id)
                completed.add(step_id)
                results[step_id] = None

                self.update_workflow_step_state(
                    step_id,
                    "skipped",
                    "Skipped by run_if=never",
                )
                continue

            if run_if == "success" and depends_on and not dep_success:
                runner.step_done(
                    f"Skipped because dependency did not succeed: {step_id}"
                )

                skipped.add(step_id)
                completed.add(step_id)
                results[step_id] = None

                self.update_workflow_step_state(
                    step_id,
                    "skipped",
                    "Skipped because dependency did not succeed",
                )
                continue

            if run_if == "failed" and not dep_failed:
                runner.step_done(
                    f"Skipped because no dependency failed: {step_id}"
                )

                skipped.add(step_id)
                completed.add(step_id)
                results[step_id] = None

                self.update_workflow_step_state(
                    step_id,
                    "skipped",
                    "Skipped because no dependency failed",
                )
                continue

            if run_if == "always":
                pass
            elif run_if not in ("success", "failed", "always", "never"):
                runner.step_done(
                    f"Skipped because run_if is invalid: {run_if}"
                )

                skipped.add(step_id)
                completed.add(step_id)
                results[step_id] = None

                self.update_workflow_step_state(
                    step_id,
                    "skipped",
                    f"Invalid run_if value: {run_if}",
                )
                continue

            ok = False
            error = ""
            output = ""
            last_result = None

            try:
                self.update_workflow_step_state(
                    step_id,
                    "running",
                    "Running workflow step",
                )

                runner.step_running(
                    index,
                    total,
                    f"workflow step {step_id}",
                )

                retry_count = int(step.get("retry_count", 0) or 0)
                retry_delay = int(step.get("retry_delay", 0) or 0)

                attempt = 0

                while True:
                    attempt += 1

                    self.update_workflow_step_state(
                        step_id,
                        "running",
                        f"Attempt {attempt} of {retry_count + 1}",
                    )

                    step_id, ok, error, output = self.run_workflow_step(name, step)
                    last_result = (step_id, ok, error, output)

                    if ok:
                        break

                    if attempt > retry_count:
                        break

                    self.update_workflow_step_state(
                        step_id,
                        "running",
                        (
                            f"Attempt {attempt} failed; retrying in "
                            f"{retry_delay}s: {error}"
                        ),
                        output,
                    )

                    if retry_delay > 0:
                        import time
                        time.sleep(retry_delay)

                step_id, ok, error, output = last_result

                if ok:
                    completed.add(step_id)
                    results[step_id] = True

                    runner.step_done(
                        f"Workflow step complete: {step_id}"
                    )

                    self.update_workflow_step_state(
                        step_id,
                        "success",
                        "Step completed",
                        output=output,
                    )
                else:
                    failed.add(step_id)
                    results[step_id] = False

                    self.update_workflow_step_state(
                        step_id,
                        "failed",
                        error,
                        output=output,
                    )

                    raise TermForgeError(error)

            except Exception as exc:
                failed.add(step_id)
                results[step_id] = False

                runner.step_failed(
                    f"Workflow step failed: {step_id}: {exc}"
                )

                failure_output = ""

                if "output" in locals() and output:
                    failure_output = output

                elif "last_result" in locals() and last_result:
                    try:
                        failure_output = last_result[3] or ""
                    except Exception:
                        failure_output = ""

                if not failure_output:
                    failure_output = str(exc)

                self.update_workflow_step_state(
                    step_id,
                    "failed",
                    str(exc),
                    output=failure_output,
                )

        self.add_history_entry(
            "workflow",
            f"{name}: {len(completed)}/{total} completed",
            source=source,
        )

        self.set_status(
            f"Workflow {name}: {len(completed)}/{total} completed."
        )

        final_status = "failed" if failed else "finished"
        self.finish_workflow_state(final_status)

        runner.finished()

    def set_current_environment(
        self,
        name: str | None,
    ) -> None:

        if name:
            templates = self.get_environment_templates()

            if name not in templates:
                raise TermForgeError(
                    f"Unknown environment template: {name}"
                )

        self.current_environment = name

        if name:
            self.set_status(
                f"Environment selected: {name}"
            )
        else:
            self.set_status(
                "Environment cleared."
            )


    def get_current_environment(self):
        return getattr(
            self,
            "current_environment",
            None,
        )

    def get_environment_templates(self) -> dict:
        templates = getattr(
            self.cfg,
            "EnvironmentTemplates",
            None,
        )

        if templates is None or not isinstance(templates, dict):
            templates = {}
            setattr(self.cfg, "EnvironmentTemplates", templates)

        return templates


    def set_environment_template(
        self,
        name: str,
        variables: dict,
    ) -> None:
        name = name.strip()

        if not name:
            raise TermForgeError(
                "Environment template name is required."
            )

        templates = self.get_environment_templates()

        cleaned = {}

        for key, value in variables.items():
            key = str(key).strip()

            if not key:
                continue

            cleaned[key] = str(value)

        templates[name] = cleaned

        setattr(
            self.cfg,
            "EnvironmentTemplates",
            templates,
        )

        self.persist_full_config()


    def delete_environment_template(
        self,
        name: str,
    ) -> None:
        templates = self.get_environment_templates()
        templates.pop(name, None)

        setattr(
            self.cfg,
            "EnvironmentTemplates",
            templates,
        )

        self.persist_full_config()


    def resolve_environment_variables(
        self,
        text: str,
        environment_name: str | None = None,
    ) -> str:

        if not isinstance(text, str):
            return text

        variables = dict(self.get_variables())

        if environment_name:
            templates = self.get_environment_templates()

            env_vars = templates.get(environment_name, {})

            if isinstance(env_vars, dict):
                variables.update(env_vars)

        def replace_var(match):
            name = match.group(1)
            return str(
                variables.get(name, match.group(0))
            )

        return re.sub(
            r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}",
            replace_var,
            text,
        )

    def window_exists(self, window_id) -> bool:
        if not window_id:
            return False

        try:
            result = subprocess.run(
                ["xdotool", "getwindowname", str(window_id)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=2,
            )

            return result.returncode == 0

        except Exception:
            return False

    def get_variables(self) -> dict:
        variables = getattr(self.cfg, "Variables", {})
        if not isinstance(variables, dict):
            variables = {}
            setattr(self.cfg, "Variables", variables)
        return variables


    def set_variable(self, name: str, value: str) -> None:
        name = name.strip()
        if not name:
            raise TermForgeError("Variable name is required.")

        variables = self.get_variables()

        if value.strip():
            variables[name] = value.strip()
        else:
            variables.pop(name, None)

        setattr(self.cfg, "Variables", variables)
        self.persist_full_config()

    def resolve_config_variables(self, text: str) -> str:
        if not isinstance(text, str):
            return text

        variables = self.get_variables()

        def replace_var(match):
            name = match.group(1)
            return str(variables.get(name, match.group(0)))

        return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", replace_var, text)

    def validate_window_profile(self, profile_name: str) -> dict:
        profiles = self.get_window_profiles()
        profile = profiles.get(profile_name)

        if profile is None:
            return {
                "name": profile_name,
                "valid": False,
                "window_id": "",
                "status": "missing",
                "message": "Profile does not exist.",
            }

        if isinstance(profile, dict):
            window_id = profile.get("window_id")
        else:
            window_id = profile

        exists = self.window_exists(window_id)

        return {
            "name": profile_name,
            "valid": exists,
            "window_id": window_id,
            "status": "valid" if exists else "stale",
            "message": "Window exists." if exists else "Window is not available.",
        }

    def validate_all_window_profiles(self) -> list[dict]:
        profiles = self.get_window_profiles()
        return [
            self.validate_window_profile(name)
            for name in sorted(profiles.keys())
        ]

    def check_config_health(self):
        issues = []

        categories = getattr(self.cfg, "Categories", {})
        if not isinstance(categories, dict):
            issues.append({
                "level": "error",
                "area": "categories",
                "name": "Categories",
                "message": "Categories must be a dictionary.",
            })
            categories = {}

        for category, commands in categories.items():
            if not isinstance(commands, dict):
                issues.append({
                    "level": "error",
                    "area": "categories",
                    "name": category,
                    "message": "Category must contain a command dictionary.",
                })
                continue

            for command_name, entry in commands.items():
                try:
                    parse_command_entry(entry)
                except Exception as exc:
                    issues.append({
                        "level": "error",
                        "area": "commands",
                        "name": f"{category}/{command_name}",
                        "message": str(exc),
                    })

        profiles = getattr(self.cfg, "Windows", {})
        if not isinstance(profiles, dict):
            issues.append({
                "level": "error",
                "area": "profiles",
                "name": "Windows",
                "message": "Windows must be a dictionary.",
            })
            profiles = {}

        for name, profile in profiles.items():
            window_id = None

            if isinstance(profile, dict):
                window_id = profile.get("window_id")
            else:
                window_id = profile

            if not window_id:
                issues.append({
                    "level": "warning",
                    "area": "profiles",
                    "name": name,
                    "message": "Profile has no window_id.",
                })
                continue

            try:
                exists = self.window_exists(window_id)
            except Exception as exc:
                exists = False
                issues.append({
                    "level": "warning",
                    "area": "profiles",
                    "name": name,
                    "message": f"Could not validate window {window_id}: {exc}",
                })

            if not exists:
                issues.append({
                    "level": "warning",
                    "area": "profiles",
                    "name": name,
                    "message": f"Window does not exist: {window_id}",
                })

        schedules = getattr(self.cfg, "Schedules", [])
        if not isinstance(schedules, list):
            issues.append({
                "level": "error",
                "area": "schedules",
                "name": "Schedules",
                "message": "Schedules must be a list.",
            })
            schedules = []

        for index, schedule in enumerate(schedules, start=1):
            if not isinstance(schedule, dict):
                issues.append({
                    "level": "error",
                    "area": "schedules",
                    "name": f"Schedule {index}",
                    "message": "Schedule must be a dictionary.",
                })
                continue

            target_type = schedule.get("target_type", "command")

            if target_type == "workflow":
                if not schedule.get("workflow"):
                    issues.append({
                        "level": "error",
                        "area": "schedules",
                        "name": schedule.get("name", f"Schedule {index}"),
                        "message": "Workflow schedule has no workflow name.",
                    })
            else:
                category = schedule.get("category")
                command = schedule.get("command")

                if category not in categories:
                    issues.append({
                        "level": "error",
                        "area": "schedules",
                        "name": schedule.get("name", f"Schedule {index}"),
                        "message": f"Unknown category: {category}",
                    })
                elif command not in categories.get(category, {}):
                    issues.append({
                        "level": "error",
                        "area": "schedules",
                        "name": schedule.get("name", f"Schedule {index}"),
                        "message": f"Unknown command: {category}/{command}",
                    })

        if not issues:
            issues.append({
                "level": "ok",
                "area": "config",
                "name": "Health",
                "message": "No issues found.",
            })

        return issues

    def get_window_profiles(self) -> dict:
        windows = getattr(self.cfg, "Windows", {})
        if not isinstance(windows, dict):
            windows = {}
            setattr(self.cfg, "Windows", windows)
        return windows


    def save_window_profiles(self) -> None:
        self.persist_full_config()


    def get_selected_window_id(self):
        for attr in (
            "selected_window_id",
            "selected_window",
            "target_window_id",
            "target_window",
            "current_window",
            "window_id",
            "win_id",
        ):
            value = getattr(self, attr, None)
            if value:
                return value

        return None


    def save_current_window_as_profile(self, profile_name: str) -> None:
        profile_name = profile_name.strip()
        if not profile_name:
            raise TermForgeError("Profile name is required.")

        window_id = self.get_selected_window_id()
        if not window_id:
            raise TermForgeError("No target window selected.")

        profiles = self.get_window_profiles()
        profiles[profile_name] = {
            "window_id": window_id,
            "backend": self.get_backend_name(),
            "tmux_session": getattr(self.cfg, "TmuxSession", "termforge"),
            "tmux_pane": getattr(self.cfg, "TmuxPane", ""),
            "tmux_mode": getattr(self.cfg, "TmuxMode", "pane"),
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        self.save_window_profiles()


    def select_window_profile(self, profile_name: str) -> None:
        profiles = self.get_window_profiles()

        profile = profiles.get(profile_name)

        if isinstance(profile, dict):
            window_id = profile.get("window_id")
        else:
            window_id = profile
            profile = {
                "window_id": window_id,
            }

        if not profile:
            raise TermForgeError(f"Unknown profile: {profile_name}")

        window_id = profile.get("window_id")
        if not window_id:
            raise TermForgeError(f"Profile has no window_id: {profile_name}")

        backend_name = profile.get("backend", "")

        if backend_name:
            if backend_name in ("x11", "subprocess", "tmux"):
                setattr(self.cfg, "Backend", backend_name)

                if backend_name == "tmux":
                    setattr(
                        self.cfg,
                        "TmuxSession",
                        profile.get(
                            "tmux_session",
                            getattr(self.cfg, "TmuxSession", "termforge"),
                        ),
                    )
                    setattr(
                        self.cfg,
                        "TmuxPane",
                        profile.get(
                            "tmux_pane",
                            getattr(self.cfg, "TmuxPane", ""),
                        ),
                    )
                    setattr(
                        self.cfg,
                        "TmuxMode",
                        profile.get(
                            "tmux_mode",
                            getattr(self.cfg, "TmuxMode", "pane"),
                        ),
                    )

                self.backend = self.create_backend()
                self.persist_full_config()

        if hasattr(self, "selected_window"):
            self.selected_window = window_id

        if hasattr(self, "selected_window_id"):
            self.selected_window_id = window_id

        self.set_status(
            f"Selected profile: {profile_name} -> {window_id} "
            f"backend:{self.get_backend_name()}"
        )

    def terminate_current_process(self) -> None:
        proc = getattr(self, "current_process", None)

        if proc is None:
            self.set_status("No running process to terminate.")
            return

        try:
            proc.terminate()
            self.set_status("Terminate signal sent to running process.")
        except Exception as exc:
            self.show_traceback_window("Terminate Running Process Failed", exc)


    def kill_current_process(self) -> None:
        proc = getattr(self, "current_process", None)

        if proc is None:
            self.set_status("No running process to kill.")
            return

        try:
            proc.kill()
            self.set_status("Kill signal sent to running process.")
        except Exception as exc:
            self.show_traceback_window("Kill Running Process Failed", exc)

    def is_execution_queue_paused(self) -> bool:
        return bool(getattr(self, "execution_queue_paused", False))

    def pause_execution_queue(self) -> None:
        self.execution_queue_paused = True
        self.set_status("Execution queue paused.")

    def resume_execution_queue(self) -> None:
        self.execution_queue_paused = False
        self.set_status("Execution queue resumed.")
        self.root.after(10, self.process_execution_queue)

    def toggle_execution_queue_pause(self) -> None:
        if self.is_execution_queue_paused():
            self.resume_execution_queue()
        else:
            self.pause_execution_queue()

    def get_execution_history(self) -> list:
        history = getattr(self.cfg, "ExecutionHistory", [])
        if not isinstance(history, list):
            history = []
            setattr(self.cfg, "ExecutionHistory", history)
        return history

    def add_execution_history(self, job: dict, status: str, error: str = "") -> None:
        history = self.get_execution_history()

        history.insert(0, {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": job.get("source", ""),
            "category": job.get("category", ""),
            "command": job.get("command", ""),
            "priority": job.get("priority", "normal"),
            "status": status,
            "error": error,
        })

        del history[200:]
        self.persist_full_config()

    def get_config_path(self) -> Path:
        return CONFIG_FILE

    def add_completed_job(self, job: dict, status: str, error: str = "") -> None:
        completed = dict(job)
        completed["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        completed["status"] = status
        completed["error"] = error

        self.completed_jobs.insert(0, completed)
        del self.completed_jobs[50:]

    def set_scheduler_paused(self, paused: bool) -> None:
        setattr(self.cfg, "SchedulerPaused", bool(paused))
        self.persist_full_config()

        state = "PAUSED" if paused else "ACTIVE"
        self.set_status(f"Scheduler: {state}")
        self.log(f"Scheduler {state.lower()}.")

    def pause_scheduler(self) -> None:
        self.set_scheduler_paused(True)

    def resume_scheduler(self) -> None:
        self.set_scheduler_paused(False)

    def toggle_scheduler(self) -> None:
        self.set_scheduler_paused(not self.is_scheduler_paused())

    def enqueue_command(
            self,
            category: str,
            command: str,
            source: str = "manual",
            priority: str = "normal",
            ) -> None:

        job = {
            "kind": "command",
            "category": category,
            "command": command,
            "source": source,
            "priority": priority if priority in PRIORITY_ORDER else "normal",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        self.execution_queue.append(job)
        self.add_execution_history(job, "queued", "")

        self.set_status(
            f"Queued {category}/{command} "
            f"({len(self.execution_queue)} pending)"
        )

        self.root.after(10, self.process_execution_queue)

    def process_execution_queue(self) -> None:
        if self.is_execution_queue_paused():
            self.set_status("Execution queue paused.")
            return

        if self.execution_running:
            return

        if not self.execution_queue:
            return

        self.execution_queue.sort(
            key=lambda job: PRIORITY_ORDER.get(job.get("priority", "normal"), 2)
        )
        job = self.execution_queue.pop(0)
        self.execution_running = True
        self.current_job = job
        self.current_job_started_at = datetime.now()

        category = job["category"]
        command = job["command"]
        source = job.get("source", "manual")

        self.add_execution_history(job, "started", "")

        try:
            self.set_status(f"Running queued command: {category}/{command}")
            self.log(f"Queue running [{source}]: {category}/{command}")

            # direct execution path
            if job.get("kind") == "workflow":
                workflow_name = job.get("workflow") or command
                self.run_workflow(workflow_name, source=source)
            else:
                self.select_cmd(None, category, command) 

            self.log(f"Queue complete [{source}]: {category}/{command}")
            self.add_completed_job(job, "success", "")
            self.add_execution_history(job, "success", "")

        except Exception as exc:
            self.log(f"Queue failed [{source}]: {category}/{command}: {exc}")
            self.add_completed_job(job, "failed", str(exc))
            self.add_execution_history(job, "failed", str(exc))

            try:
                self.show_traceback_window(
                    f"Queued Command Failed: {category}/{command}",
                    exc,
                )
            except Exception:
                pass

        finally:
            self.current_job = None
            self.current_job_started_at = None
            self.execution_running = False

            if self.execution_queue:
                self.root.after(100, self.process_execution_queue)

    def get_backup_dir(self) -> Path:
        backup_dir = Path(getattr(self.cfg, "BackupDir", CONFIG_DIR / "backups"))
        backup_dir.mkdir(parents=True, exist_ok=True)
        return backup_dir

    def create_config_backup(self):
        backup_dir = CONFIG_DIR / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        target = backup_dir / f"termforge-config-{timestamp}.py"

        source = CONFIG_DIR / "config.py"

        if not source.exists():
            raise FileNotFoundError(f"Config file not found: {source}")

        shutil.copy2(source, target)

        return target

    def create_automatic_backup(self) -> str:
        target = create_config_backup()
        return str(target)

    def export_full_config(self) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")

        target = filedialog.asksaveasfilename(
            title="Export TermForge Configuration",
            defaultextension=".py",
            initialfile=f"termforge_backup_{timestamp}.py",
            filetypes=[
                ("Python files", "*.py"),
                ("All files", "*.*"),
            ],
        )

        if not target:
            return

        shutil.copy2(CONFIG_FILE, target)

        prune_config_backups(backup_dir, keep=25)

        self.set_status(f"Exported configuration to {target}")
        messagebox.showinfo("Export Configuration", f"Exported to:\n\n{target}")

    def prune_config_backups(backup_dir: Path, keep: int = 25) -> None:
        backups = sorted(
            backup_dir.glob("termforge-config-*.py"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        for path in backups[keep:]:
            try:
                path.unlink()
            except Exception:
                pass

    def import_full_config(self, filename):
        shutil.copy2(
            filename,
            self.config_file,
        )

        self.reload_config()

    def restore_config_backup(self, filename):
        source = Path(filename)

        if not source.exists():
            raise FileNotFoundError(
                f"Backup file not found: {source}"
            )

        config_file = Path(self.config_path)

        # Safety backup of current config first
        backup_file = config_file.with_suffix(".pre_restore.bak")

        if config_file.exists():
            shutil.copy2(config_file, backup_file)

        shutil.copy2(source, config_file)

        self.reload_config()

        self.set_status(
            f"Restored configuration from {source.name}"
        )

        return str(config_file)

    def is_scheduler_paused(self) -> bool:
        return bool(getattr(self.cfg, "SchedulerPaused", False))

    def set_scheduler_paused(self, paused: bool) -> None:
        setattr(self.cfg, "SchedulerPaused", bool(paused))
        self.persist_full_config()

        state = "PAUSED" if paused else "ACTIVE"
        self.set_status(f"Scheduler: {state}")
        self.log(f"Scheduler {state.lower()}.")

    def pause_scheduler(self) -> None:
        self.set_scheduler_paused(True)

    def resume_scheduler(self) -> None:
        self.set_scheduler_paused(False)

    def toggle_scheduler(self) -> None:
        self.set_scheduler_paused(not self.is_scheduler_paused())

    def get_chain_runner(self, total_steps: int):
        runner = getattr(self, "chain_runner_window", None)

        if runner is None or not runner.exists():
            runner = ChainRunnerWindow(self.root, total_steps)
            self.chain_runner_window = runner
        else:
            runner.reset_for_run(total_steps)

        return runner

    def get_tags(self) -> dict:
        tags = getattr(self.cfg, "Tags", {})
        if not isinstance(tags, dict):
            tags = {}
            setattr(self.cfg, "Tags", tags)
        return tags

    def command_key(self, category: str, name: str) -> str:
        return f"{category}/{name}"

    def get_command_tags(self, category: str, name: str) -> list[str]:
        tags = self.get_tags()
        value = tags.get(self.command_key(category, name), [])
        if not isinstance(value, list):
            return []
        return [str(tag).strip() for tag in value if str(tag).strip()]

    def set_command_tags(self, category: str, name: str, tag_text: str) -> None:
        tags = self.get_tags()
        key = self.command_key(category, name)

        parsed = [
            tag.strip()
            for tag in re.split(r"[,\s]+", tag_text)
            if tag.strip()
        ]

        if parsed:
            tags[key] = parsed
        else:
            tags.pop(key, None)

        self.persist_full_config()

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

        if isinstance(cmd, str) and self.is_dangerous_command(cmd):
            if not self.confirm_dangerous_command(cmd):
                raise TermForgeError("Command cancelled by user.")

        self.run_cmd(cmd_type, cmd, options, None)

    def is_dangerous_command(self, cmd: str) -> bool:
        cmd_lower = cmd.lower()
        dangerous_patterns = [
            "sudo",
            "rm -rf",
            "mkfs",
            "dd ",
            "shutdown",
            "reboot",
            "poweroff",
            "systemctl",
            ":(){:|:&};:",
        ]
        return any(pattern in cmd_lower for pattern in dangerous_patterns)

    def confirm_dangerous_command(self, cmd: str) -> bool:
        return messagebox.askokcancel(
            "Dangerous Command",
            f"This command may be dangerous:\n\n{cmd}\n\nContinue?"
        )

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

    def get_hotkeys_dict(self) -> dict:
        hotkeys = getattr(self.cfg, "Hotkeys", None)
        if hotkeys is None or not isinstance(hotkeys, dict):
            hotkeys = {}
            setattr(self.cfg, "Hotkeys", hotkeys)
        return hotkeys

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
            self.show_traceback_window("Could not persist disabled plugins: ", exc)

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
                self.show_tracback_window(f"Skipping hotkey {hotkey!r}: ", exc)
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
            self.show_traceback_window("Could not start global hotkeys: ", exc)
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
                self.show_traceback_window(f"{errors[name]}", exc)
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
            self.show_traceback_window("Plugin Folder", str(exc))

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
        timeout = 20

        if not isinstance(payload, dict):
            raise TermForgeError(
                f"xdo helper payload must be a dict: {payload!r}"
            )

        if not payload.get("action"):
            raise TermForgeError(
                f"xdo helper payload missing action: {payload!r}"
            )

        command = [
            sys.executable,
            "-m",
            "termforge.xdo_helper",
        ]

        if payload.get("action") == "select_window":
            timeout = 120

        proc = subprocess.run(
            command,
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )

        if proc.returncode != 0:
            raise TermForgeError(
                "xdo helper failed:\n\n"
                f"payload:\n{pprint.pformat(payload)}\n\n"
                f"stdout:\n{proc.stdout}\n\n"
                f"stderr:\n{proc.stderr}"
            )

        try:
            data = json.loads(proc.stdout or "{}")
        except Exception as exc:
            raise TermForgeError(
                "xdo helper returned invalid JSON:\n\n"
                f"stdout:\n{proc.stdout}\n\n"
                f"stderr:\n{proc.stderr}"
            ) from exc

        ok = data.get("ok", False) or data.get("status") == "ok"

        if not ok:    
            raise TermForgeError(
                "xdo helper reported failure:\n\n"
                f"{pprint.pformat(data)}"
            )

        return data

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
            self.show_traceback_window(f"Initial selection skipped: ", exc)

    def forget_saved_window(self) -> None:
        self.window_id = None
        self.last_window_id = None
        self.save_state()
        self.set_status("Forgot remembered window.")

    def select_target_window(self) -> None:
        self.root.withdraw()
        self.root.update_idletasks()
        self.root.update()

        try:
            result = self._run_helper(
                {
                    "action": "get_active_window_after_delay",
                    "delay": 3,
                }
            )
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
            self.show_traceback_window("Target Window", str(exc))

    def select_profile(self, profile_name: str) -> None:
        self.select_window_profile(profile_name)

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

        runner = self.get_chain_runner(total)

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

                if step_kind == "environment":
                    if len(step) < 2:
                        raise TermForgeError("environment step requires an environment template name.")

                    environment_name = str(step[1]).strip()

                    runner.step_running(index, total, f"environment {environment_name}")
                    self.set_current_environment(environment_name)
                    runner.step_done(f"Using environment {environment_name}")
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

                if isinstance(step_cmd, str) and self.is_dangerous_command(step_cmd):
                    if not self.confirm_dangerous_command(step_cmd):
                        runner.step_failed("Command cancelled by user.")
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
                self.show_traceback_window(f"{runner.step_failed}", exc)

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
        if options is None:
            options = {}

        normalized = cmd_type
        if isinstance(cmd_type, str):
            normalized = cmd_type.strip().lower()

        try:
            if normalized == "chain":
                self.run_chain(cmd, source="chain")
                return

            resolved_cmd = cmd

            if (
                normalized in (1, 2, 3, "spawn", "command", "send", "detached")
                and isinstance(cmd, str)
            ):
                resolved_cmd = self.resolve_command_placeholders(
                    cmd,
                    shared_vars=shared_vars,
                )

                if resolved_cmd is None:
                    return

                resolved_cmd = self.resolve_environment_variables(
                    resolved_cmd,
                    self.get_current_environment(),
                )

                resolved_cmd = self.resolve_shared_variables_in_text(
                    resolved_cmd
                )

            if isinstance(resolved_cmd, str) and self.is_dangerous_command(resolved_cmd):
                if not options.get("confirm", False):
                    if not self.confirm_dangerous_command(resolved_cmd):
                        self.set_status("Command cancelled.")
                        return

            if not self.confirm_command(normalized, resolved_cmd, options):
                self.set_status("Command cancelled by user.")
                return

            if not hasattr(self, "backend") or self.backend is None:
                self.backend = self.create_backend()

            if normalized in (0, "select"):
                self.backend.select_target()

            elif normalized in (1, "spawn"):
                self.spawn_terminal(
                    str(resolved_cmd),
                    record_history=record_history,
                )

            elif normalized in (2, "command", "send"):
                self.backend.send_text(
                    str(resolved_cmd),
                    record_history=record_history,
                )

            elif normalized in (3, "detached"):
                self.backend.run_detached(
                    str(resolved_cmd),
                    record_history=record_history,
                )

            elif normalized == "plugin":
                self.run_plugin(cmd)

            else:
                raise TermForgeError(f"Unknown command type: {cmd_type}")

        except Exception as exc:
            self.show_traceback_window("Command failed", exc)

    def poll_current_process(self) -> None:
        proc = getattr(self, "current_process", None)

        if proc is None:
            return

        try:
            code = proc.poll()
        except Exception:
            self.current_process = None
            self.current_process_job = None
            return

        if code is not None:
            job = getattr(self, "current_process_job", None) or {}

            try:
                self.add_execution_history(
                    {
                        "source": job.get("source", "detached"),
                        "category": job.get("category", ""),
                        "command": job.get("command", ""),
                        "priority": job.get("priority", "normal"),
                    },
                    "process_exit",
                    f"exit_code={code}",
                )
            except Exception:
                pass

            self.current_process = None
            self.current_process_job = None
            self.set_status(f"Detached process exited with code {code}")

    def get_schedule_history(self) -> list:
        history = getattr(self.cfg, "ScheduleHistory", [])
        if not isinstance(history, list):
            history = []
            setattr(self.cfg, "ScheduleHistory", history)
        return history

    def add_schedule_history(self, schedule: dict, status: str, error: str = "") -> None:
        history = self.get_schedule_history()
        history.insert(0, {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "name": schedule.get("name", ""),
            "target_type": schedule.get("target_type", "command"),
            "category": schedule.get("category", ""),
            "command": schedule.get("command", ""),
            "workflow": schedule.get("workflow", ""),
            "profile": schedule.get("profile", ""),
            "priority": schedule.get("priority", "normal"),
            "type": schedule.get("type", ""),
            "status": status,
            "error": error,
        })
        del history[200:]

    def get_schedules(self) -> list:
        schedules = getattr(self.cfg, "Schedules", [])
        if not isinstance(schedules, list):
            schedules = []
            setattr(self.cfg, "Schedules", schedules)
        return schedules

    def run_scheduled_command(self, schedule: dict) -> None:
        from datetime import datetime

        category = schedule.get("category")
        command = schedule.get("command")
        target_type = schedule.get("target_type", "command")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        schedule["_last_run"] = now
        schedule["_run_count"] = int(schedule.get("_run_count", 0) or 0) + 1

        self.log(f"Scheduled command running: {category}/{command}")

        categories = getattr(self.cfg, "Categories", {})

        backend_ctx = self.snapshot_backend_context()

        try:
            self.apply_backend_override(schedule)

            priority = schedule.get("priority", "normal")
            if priority not in PRIORITY_ORDER:
                priority = "normal"

            if target_type == "workflow":
                workflow_name = schedule.get("workflow", "").strip()

                if not workflow_name:
                    raise TermForgeError(
                        "Workflow schedule requires a workflow name."
                    )

                self.log(
                    f"Scheduled workflow queued: {workflow_name}"
                )

                self.enqueue_workflow(
                    workflow_name,
                    source="schedule",
                    priority=priority,
                )

                schedule["_last_status"] = "queued"
                schedule["_last_error"] = ""

                self.add_schedule_history(schedule, "queued", "")
                self.log(f"Scheduled workflow queued: {workflow_name}")

                self.show_toast(
                    f"✓ Scheduled workflow queued:\n{workflow_name}"
                )

            else:
                if category not in categories:
                    raise TermForgeError(
                        f"Scheduled category not found: {category}"
                    )

                if command not in categories[category]:
                    raise TermForgeError(
                        f"Scheduled command not found: {category}/{command}"
                    )

                entry = categories[category][command]
                _cmd_type, _cmd, _options = parse_command_entry(entry)

                profile = schedule.get("profile", "").strip()

                if profile:
                    self.log(
                        f"Scheduled command selecting profile: {profile}"
                    )
                    self.select_window_profile(profile)

                self.set_status(
                    f"Queueing scheduled command: "
                    f"{category}/{command}"
                )

                self.log(
                    f"Scheduled command queued: "
                    f"{category}/{command}"
                )

                self.enqueue_command(
                    category,
                    command,
                    source="schedule",
                    priority=priority,
                )

                schedule["_last_status"] = "queued"
                schedule["_last_error"] = ""

                self.add_schedule_history(schedule, "queued", "")
                self.log(f"Scheduled command queued: {category}/{command}")

                self.show_toast(
                    f"✓ Scheduled command queued:\n{category}/{command}"
                )

        except Exception as exc:
            schedule["_last_status"] = "failed"
            schedule["_last_error"] = str(exc)

            self.add_schedule_history(schedule, "failed", str(exc))
            self.log(f"Scheduled command failed: {category}/{command}: {exc}")

            self.show_toast(
                f"✗ Scheduled command failed:\n{category}/{command}"
            )

            try:
                self.show_traceback_window(
                    f"Scheduled Command Failed: {category}/{command}",
                    exc,
                )

                self.log(
                    f"Scheduled command failed: {category}/{command}: ",
                    exc,
                )

            except Exception:
                pass

        finally:
            self.restore_backend_context(backend_ctx)
            self.persist_full_config()

    def run_startup_schedules(self) -> None:
        if self.is_scheduler_paused():
            self.set_status("Scheduler paused; startup schedules skipped.")
            return
        for schedule in self.get_schedules():
            if schedule.get("enabled") and schedule.get("type") == "startup":
                self.run_scheduled_command(schedule)


    def scheduler_tick(self) -> None:
        from datetime import datetime

        now = datetime.now()

        if self.is_scheduler_paused():
            self.root.after(30_000, self.scheduler_tick)
            return

        now_hhmm = now.strftime("%H:%M")

        for schedule in self.get_schedules():
            if not schedule.get("enabled"):
                continue

            schedule_type = schedule.get("type")

            if schedule_type == "daily":
                if schedule.get("time") == now_hhmm:
                    last_run_key = now.strftime("%Y-%m-%d %H:%M")

                    if schedule.get("_last_run") != last_run_key:
                        schedule["_last_run"] = last_run_key
                        self.run_scheduled_command(schedule)

            elif schedule_type == "interval_minutes":
                minutes = int(schedule.get("minutes", 0) or 0)

                if minutes > 0:
                    current_tick = int(now.timestamp() // (minutes * 60))

                    if schedule.get("_last_tick") != current_tick:
                        schedule["_last_tick"] = current_tick
                        self.run_scheduled_command(schedule)

        self.persist_full_config()

        # run again in 30 seconds
        self.root.after(30_000, self.scheduler_tick)

    def start_scheduler(self) -> None:
        self.run_startup_schedules()
        self.root.after(30_000, self.scheduler_tick)

    def select_cmd(self, parent_window, category: str, subcategory: str) -> None:
        entry = self.cfg.Categories[category][subcategory]
        cmd_type, cmd, options = parse_command_entry(entry)

        self.add_recent(category, subcategory)
        self.add_usage(category, subcategory)

        self.run_cmd(cmd_type, cmd, options, parent_window)

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

    def export_config_backup(self) -> None:
        try:
            if not CONFIG_FILE.exists():
                self.show_traceback_window("Export Config", "Config file does not exist yet.")
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
            self.show_traceback_window("Export Config", exc)

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
                self.show_traceback_window("Import Config", "Could not read selected config file.")
                return

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            if not hasattr(module, "Categories"):
                self.show_traceback_window("Import Config", "Selected file does not contain Categories.")
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
            self.traceback_window("Import Config", str(exc))

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
                self.show_traceback_window("Reload failed", str(exc))
            else:
                self.log(f"Silent reload failed: {exc}")

    def bind_global_shortcuts(self) -> None:
        self.root.bind_all("<Control-p>", self.open_command_palette)
        self.root.bind_all("<Control-P>", self.open_command_palette)

    def persist_full_config(self) -> None:
        import time

        now = time.time()

        try:
            backup_minutes = int(getattr(self.cfg, "AutoBackupMinutes", 30))
        except Exception:
            backup_minutes = 30

        if backup_minutes > 0:
            if now - getattr(self, "_last_backup_time", 0) > backup_minutes * 60:
                try:
                    self.create_automatic_backup()
                    self._last_backup_time = now
                except Exception:
                    pass

        try:
            skip_names = {
                "__builtins__",
                "__cached__",
                "__doc__",
                "__file__",
                "__loader__",
                "__name__",
                "__package__",
                "__spec__",
            }

            skip_prefixes = ("_",)

            lines = [
                "# TermForge user configuration",
                "# Auto-generated by TermForge.",
                "",
            ]

            for name in sorted(dir(self.cfg)):
                if name in skip_names:
                    continue

                if name.startswith(skip_prefixes):
                    continue

                value = getattr(self.cfg, name)

                if callable(value):
                    continue

                if hasattr(value, "__module__") and value.__module__ not in (
                    "builtins",
                    "__builtin__",
                ):
                    continue

                lines.append(
                    f"{name} = {pprint.pformat(value, indent=4)}"
                )

            lines.append("")

            CONFIG_FILE.write_text(
                "\n".join(lines),
                encoding="utf-8",
            )

        except Exception as exc:
            self.show_traceback_window(
                "Could not persist full config: ",
                exc,
            )

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
        file_menu.add_command(
            label="Export Full Configuration",
            command=self.export_full_config,
        )
        file_menu.add_command(
            label="Import Full Configuration",
            command=self.import_full_config,
        )
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        tools_menu = Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Settings", command=self.open_settings)
        tools_menu.add_command(label="Workflow Variables", command=self.open_workflow_variables)
        tools_menu.add_command(label="Workflow Picker", command=self.open_workflow_picker)
        tools_menu.add_separator()
        tools_menu.add_command(label="Command Palette\tCtrl+P", command=self.open_command_palette)
        tools_menu.add_command(label="Command / Chain Editor", command=self.open_command_editor)
        tools_menu.add_command(label="Category Editor", command=self.open_category_editor)
        tools_menu.add_command(label="Workflow Editor", command=self.open_workflow_editor)
        tools_menu.add_command(label="Tag Manager", command=self.open_tag_manager)
        tools_menu.add_command(label="Plugin Manager", command=self.open_plugin_manager)
        tools_menu.add_separator()
        tools_menu.add_command(label="Terminal Output Viewer", command=self.open_terminal_output_viewer)
        tools_menu.add_separator()
        tools_menu.add_command(label="Hotkeys", command=self.show_hotkeys_help)
        tools_menu.add_command(label="Hotkey Editor", command=self.open_hotkey_editor)
        tools_menu.add_separator()
        tools_menu.add_command(label="Reload Plugins", command=self.reload_plugins_with_notice)
        tools_menu.add_command(label="Open Plugin Folder", command=self.open_plugin_folder)
        tools_menu.add_separator()
        tools_menu.add_command(label="Shared Variable Manager", command=self.open_shared_variable_manager)
        tools_menu.add_separator()
        tools_menu.add_command(label="Backend Output Viewer", command=self.open_backend_output_viewer)
        menubar.add_cascade(label="Tools", menu=tools_menu)

        automation_menu = Menu(menubar, tearoff=0)
        automation_menu.add_command(label="Schedule Manager", command=self.open_schedule_manager)
        automation_menu.add_command(label="Schedule History", command=self.open_schedule_history)
        automation_menu.add_command(label="Execution Queue", command=self.open_execution_queue)
        automation_menu.add_separator()
        automation_menu.add_command(label="History", command=self.open_history_window)
        automation_menu.add_separator()
        automation_menu.add_command(label="Select Target Window", command=self.select_target_window_with_notice)
        automation_menu.add_command(label="Reuse Saved Window", command=self.reuse_last_window)
        automation_menu.add_command(label="Forget Saved Window", command=self.forget_saved_window)
        automation_menu.add_separator()
        automation_menu.add_command(label="Pause Scheduler", command=self.pause_scheduler)
        automation_menu.add_command(label="Resume Scheduler", command=self.resume_scheduler)
        automation_menu.add_command(label="Toggle Scheduler Pause", command=self.toggle_scheduler)
        automation_menu.add_separator()
        automation_menu.add_command(label="Pause Execution Queue", command=self.pause_execution_queue)
        automation_menu.add_command(label="Resume Execution Queue", command=self.resume_execution_queue)
        automation_menu.add_command(label="Toggle Execution Queue Pause", command=self.toggle_execution_queue_pause)
        automation_menu.add_separator()
        automation_menu.add_command(label="Workflow Manager", command=self.open_workflow_manager,)
        automation_menu.add_command(label="Workflow Live Monitor", command=self.open_workflow_live_monitor,)
        automation_menu.add_command(label="Workflow History Viewer", command=self.open_workflow_history_viewer,)
        menubar.add_cascade(label="Automation", menu=automation_menu)

        profiles_menu = Menu(menubar, tearoff=0)
        profiles_menu.add_command(label="Backend Manager", command=self.open_backend_manager,)
        profiles_menu.add_command(label="Profile Manager", command=self.open_profile_manager)
        profiles_menu.add_command(label="Config Health Check", command=self.open_config_health_check,)
        profiles_menu.add_command(label="Backup Manager", command=self.open_backup_manager)
        profiles_menu.add_command(label="Variable Manager", command=self.open_variable_manager)
        profiles_menu.add_command(label="Environment Templates", command=self.open_environment_templates,)
        menubar.add_cascade(label="Profiles", menu=profiles_menu)

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
