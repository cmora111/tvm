from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time


def emit(payload: dict, code: int = 0) -> None:
    sys.stdout.write(json.dumps(payload))
    sys.stdout.flush()
    raise SystemExit(code)


def require_tool(name: str) -> None:
    if shutil.which(name) is None:
        emit({"status": "error", "error": f"Required tool '{name}' was not found in PATH."}, code=1)


def run_command(args: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        emit({"status": "error", "error": f"Command timed out: {' '.join(args)}"}, code=1)


def parse_window_id_from_xwininfo(output: str) -> int | None:
    for line in output.splitlines():
        if "Window id:" in line:
            parts = line.strip().split()
            for i, token in enumerate(parts):
                if token == "id:" and i + 1 < len(parts):
                    raw = parts[i + 1]
                    try:
                        return int(raw, 16) if raw.startswith("0x") else int(raw)
                    except ValueError:
                        return None
    return None


def select_window() -> None:
    require_tool("xwininfo")
    proc = run_command(["xwininfo"], timeout=60)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        emit({"status": "error", "error": f"xwininfo failed while selecting a window. {err}"}, code=1)
    window_id = parse_window_id_from_xwininfo(proc.stdout)
    if not window_id:
        emit({"status": "error", "error": "Could not determine selected window id from xwininfo output."}, code=1)
    emit({"status": "ok", "window_id": window_id})


def validate_window(payload: dict) -> None:
    require_tool("xprop")
    window_id = str(payload["window_id"])
    proc = run_command(["xprop", "-id", window_id], timeout=10)
    emit({"status": "ok", "valid": proc.returncode == 0})


def get_active_window() -> str:
    proc = run_command(["xdotool", "getactivewindow"], timeout=10)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        emit({"status": "error", "error": f"Could not get active window. {err}"}, code=1)
    active = (proc.stdout or "").strip()
    if not active:
        emit({"status": "error", "error": "xdotool returned no active window id."}, code=1)
    return active


def send_to_window(payload: dict) -> None:
    require_tool("xdotool")
    window_id = str(payload["window_id"])
    text = str(payload.get("text", ""))
    key = str(payload.get("key", "Return"))
    focus_delay_ms = int(payload.get("focus_delay_ms", 150))

    proc = run_command(["xdotool", "windowactivate", "--sync", window_id], timeout=15)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        emit({"status": "error", "error": f"Could not activate window {window_id}. {err}"}, code=1)

    if focus_delay_ms > 0:
        time.sleep(focus_delay_ms / 1000.0)

    active_window = get_active_window()
    if active_window != window_id:
        emit({"status": "error", "error": f"Selected window did not become active. selected={window_id}, active={active_window}"}, code=1)

    if text:
        proc = run_command(["xdotool", "type", "--clearmodifiers", "--delay", "1", text], timeout=30)
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            emit({"status": "error", "error": f"Could not type into active window {active_window}. {err}"}, code=1)

    if key:
        proc = run_command(["xdotool", "key", "--clearmodifiers", key], timeout=15)
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            emit({"status": "error", "error": f"Could not send key '{key}' to active window {active_window}. {err}"}, code=1)

    emit({"status": "ok", "window_id": window_id, "active_window": active_window})


def main() -> None:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        emit({"status": "error", "error": f"Invalid JSON payload: {exc}"}, code=1)

    action = payload.get("action")
    if action == "select_window":
        select_window()
    elif action == "send":
        send_to_window(payload)
    elif action == "validate_window":
        validate_window(payload)
    else:
        emit({"status": "error", "error": f"Unknown action: {action!r}"}, code=1)


if __name__ == "__main__":
    main()
