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

from file_lock import lock_file as _lock_file, unlock_file as _unlock_file

MAX_ENTRIES = 100


def default_log_path() -> str:
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    return os.path.join(base, "PCCleaner", "history.json")


def read_history(log_file: str = None) -> list:
    path = log_file or default_log_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def log_cleanup(entry: dict, log_file: str = None) -> bool:
    """entry example:
    {"timestamp": "2026-07-20T14:30:00", "categories": ["user_temp", ...],
     "bytes_freed": 123456789, "mode": "manual"}

    This app can write a history entry from more than one place that
    may run at close to the same moment: the GUI's Quick Clean tab, its
    Junk Cleanup tab, and the separately-launched scheduled auto-clean
    task (a different OS process). The read-modify-write here (read
    the list, append, write it back) is wrapped in an exclusive file
    lock so two of those finishing close together can't silently lose
    one entry — without the lock, whichever one WRITES second would
    overwrite the file with a list built from a "before" read that
    didn't yet include the other's entry.

    Opens with mode "a+" rather than checking os.path.exists() and
    separately creating the file first: that separate check-then-create
    step used to run OUTSIDE the lock, leaving its own race window
    where one thread's unconditional (re)creation of a "just append,
    it must be new" file could run after another thread had already
    written a real entry into it — silently wiping that entry out. "a+"
    creates the file if missing and never truncates an existing one,
    so file creation and the locked read-modify-write become one
    atomic step with no gap between them.
    """
    path = log_file or default_log_path()
    try:
        folder = os.path.dirname(path)
        if folder:
            os.makedirs(folder, exist_ok=True)

        with open(path, "a+", encoding="utf-8") as f:
            _lock_file(f)
            try:
                f.seek(0)
                content = f.read()
                try:
                    history = json.loads(content) if content.strip() else []
                    if not isinstance(history, list):
                        history = []
                except json.JSONDecodeError:
                    history = []

                history.append(entry)
                history = history[-MAX_ENTRIES:]

                f.seek(0)
                f.truncate()
                json.dump(history, f, ensure_ascii=False, indent=2)
            finally:
                _unlock_file(f)
        return True
    except OSError:
        return False
