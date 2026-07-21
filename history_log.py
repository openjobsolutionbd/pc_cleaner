"""
history_log.py
---------------
Keeps a small local record of past cleanup runs: date, which categories
were cleaned, and how many bytes were freed. Stored as JSON so it's easy
to read back and easy to inspect/delete manually if the user ever wants to.
"""

import os
import json
import tempfile

MAX_ENTRIES = 100


def default_log_path() -> str:
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    return os.path.join(base, "WindowsCleaner", "history.json")


def read_history(log_file: str = None) -> list:
    path = log_file or default_log_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def log_cleanup(entry: dict, log_file: str = None) -> bool:
    """entry example:
    {"timestamp": "2026-07-20T14:30:00", "categories": ["user_temp", ...],
     "bytes_freed": 123456789, "mode": "manual"}
    """
    path = log_file or default_log_path()
    try:
        folder = os.path.dirname(path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        history = read_history(path)
        history.append(entry)
        history = history[-MAX_ENTRIES:]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False
