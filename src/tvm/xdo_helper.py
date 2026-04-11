from __future__ import annotations

import json
import sys
import time

try:
    from xdo import Xdo
except Exception as exc:  # pragma: no cover - import depends on system package state
    Xdo = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


def emit(payload: dict, code: int = 0) -> None:
    sys.stdout.write(json.dumps(payload))
    sys.stdout.flush()
    raise SystemExit(code)


def main() -> None:
    if Xdo is None:
        emit(
            {
                "status": "error",
                "error": (
                    "Missing xdo binding. Install an X11/libxdo Python binding and the system libxdo package. "
                    f"Import error: {IMPORT_ERROR}"
                ),
            },
            code=1,
        )

    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        emit({"status": "error", "error": f"Invalid JSON payload: {exc}"}, code=1)

    action = payload.get("action")
    xdo = Xdo()

    try:
        if action == "select_window":
            window_id = xdo.select_window_with_click()
            emit({"status": "ok", "window_id": window_id})

        if action == "send":
            window_id = payload["window_id"]
            text = payload.get("text", "")
            key = payload.get("key", "Return")
            focus_delay_ms = int(payload.get("focus_delay_ms", 100))
            text_delay_us = int(payload.get("text_delay_us", 1200))
            key_delay_us = int(payload.get("key_delay_us", 1200))

            xdo.focus_window(window_id)
            if focus_delay_ms > 0:
                time.sleep(focus_delay_ms / 1000.0)

            text_bytes = text if isinstance(text, bytes) else str(text).encode()
            key_bytes = key if isinstance(key, bytes) else str(key).encode()

            xdo.enter_text_window(window_id, text_bytes, delay=text_delay_us)
            xdo.send_keysequence_window(window_id, key_bytes, delay=key_delay_us)
            emit({"status": "ok"})

        emit({"status": "error", "error": f"Unknown action: {action!r}"}, code=1)
    except Exception as exc:
        emit({"status": "error", "error": str(exc)}, code=1)


if __name__ == "__main__":
    main()
