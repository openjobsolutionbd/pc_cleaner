"""
settings.py
-----------
Tiny local settings file for PC Cleaner (currently just the screen
language). Stored as JSON next to history.json / error_log.json:
%LOCALAPPDATA%\\PCCleaner\\settings.json

Nothing here ever raises: a missing or damaged file simply means
"use the defaults", and a failed save returns False. Settings never
leave this PC.
"""

import json
import os
import tempfile

import i18n


def default_path() -> str:
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    return os.path.join(base, "PCCleaner", "settings.json")


def load_settings(path: str = None) -> dict:
    path = path or default_path()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(data: dict, path: str = None) -> bool:
    """Writes via a temp file + os.replace so a crash mid-write can't
    leave a half-written settings file behind."""
    path = path or default_path()
    tmp = None
    try:
        folder = os.path.dirname(path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=folder or None, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except OSError:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        return False


def get_language(path: str = None) -> str:
    lang = load_settings(path).get("language")
    return lang if lang in i18n.LANGS else i18n.DEFAULT_LANG


def set_language(lang: str, path: str = None) -> bool:
    if lang not in i18n.LANGS:
        return False
    data = load_settings(path)
    data["language"] = lang
    return save_settings(data, path)
