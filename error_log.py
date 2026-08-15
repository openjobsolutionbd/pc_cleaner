"""
error_log.py
------------
Central error log for PC Cleaner. This is the core of the app's
automatic safety net.

Why this exists
----------------
Instead of an unexpected bug crashing the app, or silently breaking one
piece of a cleanup run with no trace, every risky spot is wrapped (see
_run_safely() and the report_callback_exception hook in pc_cleaner.py,
and the per-category try/except in shutdown_clean.py) so that ANY
unexpected exception is caught, written here with full context, and
the app keeps running.

This changes what "finding a bug" means. Instead of reading through the
whole codebase hypothesizing about what *might* go wrong, this file
holds a short, concrete record of what *actually* went wrong, with the
exact function name and traceback — normally enough to fix on the
first look, no re-reading everything required. An empty log means
nothing broke.

Storage
-------
%LOCALAPPDATA%\\PCCleaner\\error_log.json — same folder as history.json
(see history_log.py), a capped JSON list of entries. Locked with
file_lock.py the same way history_log.py locks its file, since the GUI
and the separately-launched shutdown-clean process can both write here
around the same moment.
"""

import os
import json
import tempfile
import traceback as _tb
from datetime import datetime

from file_lock import lock_file as _lock_file, unlock_file as _unlock_file

MAX_ENTRIES = 200


def default_log_path() -> str:
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    return os.path.join(base, "PCCleaner", "error_log.json")


def record(context: str, exc: BaseException, tb_str: str = None, log_file: str = None) -> bool:
    """Append one error entry and return True on success.

    context: a short label for where this happened (e.g. a worker
        function name or "gui_callback") — this is what lets a future
        read of the log point straight at the right spot instead of
        needing to search for it.
    exc: the caught exception object.
    tb_str: optional pre-formatted traceback string. If omitted, it's
        built from exc.__traceback__ (works when called from directly
        inside an `except` block).

    Deliberately never lets an exception escape to the caller —
    logging a failure must never itself become a new failure that
    needs debugging. On any problem writing the log, this just returns
    False instead of raising.
    """
    path = log_file or default_log_path()
    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "context": context,
        "error_type": type(exc).__name__,
        "message": str(exc),
        "traceback": tb_str or "".join(_tb.format_exception(type(exc), exc, exc.__traceback__)),
    }
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
                    entries = json.loads(content) if content.strip() else []
                    if not isinstance(entries, list):
                        entries = []
                except json.JSONDecodeError:
                    entries = []

                entries.append(entry)
                entries = entries[-MAX_ENTRIES:]

                f.seek(0)
                f.truncate()
                json.dump(entries, f, ensure_ascii=False, indent=2)
            finally:
                _unlock_file(f)
        return True
    except OSError:
        return False


def read_errors(log_file: str = None) -> list:
    path = log_file or default_log_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def clear_errors(log_file: str = None) -> bool:
    """Deletes the error log file. Returns True if the file is gone
    afterward (including when it never existed)."""
    path = log_file or default_log_path()
    try:
        if os.path.exists(path):
            os.remove(path)
        return True
    except OSError:
        return False


def count_errors(log_file: str = None) -> int:
    return len(read_errors(log_file))
