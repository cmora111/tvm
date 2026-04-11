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
LOG_FILE = CONFIG_DIR / "tvm.log"
XDO_TIMEOUT_SECONDS = 12


# Logging is intentionally initialized early so startup and helper errors are captured.
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
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

        if self.debug:
            logging.getLogger().setLevel(logging.DEBUG)

        self.log("TVM starting")
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
        if "" in cmd:
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

    def _run_xdo_helper(self, payload: dict) -> dict:
        command = [sys.executable, "-m", "tvm.xdo_helper"]
        self.log(f"Running xdo helper action={payload.get('action')} payload={payload}")

        try:
            proc = subprocess.run(
                command,
                input=json.dumps(payload),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=XDO_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise TVMError("xdo helper timed out.") from exc
        except Exception as exc:  # pragma: no cover - defensive wrapper for system issues
            raise TVMError(f"Could not start xdo helper: {exc}") from exc

        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()

        if stderr:
            logging.warning("xdo helper stderr: %s", stderr)

        if proc.returncode != 0:
            raise TVMError(
                f"xdo helper exited with code {proc.returncode}."
                + (f" Details: {stderr}" if stderr else "")
            )

        if not stdout:
            raise TVMError(
                "xdo helper returned no data. The native xdo library may have crashed."
            )

        try:
            result = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise TVMError(f"xdo helper returned invalid JSON: {stdout!r}") from exc

        if result.get("status") != "ok":
            raise TVMError(result.get("error", "xdo helper reported an unknown error."))

        return result

    def select_target_window(self) -> None:
        self.root.withdraw()
        try:
            result = self._run_xdo_helper({"action": "select_window"})
        finally:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()

        selected = result.get("window_id")
        if not selected:
            raise TVMError("No window selected.")

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
                raise TVMError(f"Unknown command type: {cmd_type}")
        except Exception as exc:
            self.show_error("Command failed", f"{exc}\n\n{traceback.format_exc()}")

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
            self._run_xdo_helper(
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
                "The target may have closed or the xdo call failed. Re-select the window and try again."
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
