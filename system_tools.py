"""
system_tools.py
----------------
Small independent maintenance utilities:
  - find_empty_folders / delete_empty_folders
  - analyze_folder (one-level-deep disk space breakdown)
  - reset_icon_cache (Windows only)

These operate on a user-chosen folder (e.g. via a folder picker in the
GUI) rather than fixed system paths, since "empty folders" and "what's
using space" only make sense relative to wherever the user is looking.
"""

import os
import shutil
import string
import subprocess
import glob

from cleaner_core import get_dir_size, is_windows


def list_drives() -> list:
    """Returns available drives as a list of dicts:
    {"path", "label", "total", "used", "free"}
    On Windows this checks each letter A-Z for a usable, ready volume.
    On other OSes (e.g. during testing) it just returns the root "/".
    """
    drives = []
    if is_windows():
        for letter in string.ascii_uppercase:
            path = f"{letter}:\\"
            if os.path.isdir(path):
                try:
                    usage = shutil.disk_usage(path)
                    drives.append({
                        "path": path,
                        "label": path,
                        "total": usage.total,
                        "used": usage.used,
                        "free": usage.free,
                    })
                except OSError:
                    continue
    else:
        try:
            usage = shutil.disk_usage("/")
            drives.append({"path": "/", "label": "/", "total": usage.total, "used": usage.used, "free": usage.free})
        except OSError:
            pass
    return drives


def get_free_space(path: str):
    """Returns (total, used, free) bytes for the drive containing `path`,
    or None if it can't be determined (e.g. path doesn't exist)."""
    try:
        usage = shutil.disk_usage(path)
        return usage.total, usage.used, usage.free
    except OSError:
        return None


def find_empty_folders(root: str) -> list:
    """Returns a list of folder paths under `root` that are empty, or
    contain only other empty folders (recursively). The root itself is
    never included, even if it happens to be empty.

    Ordered deepest-first, so the list is already safe to delete in order
    (a child's emptiness is resolved before its parent is considered).
    """
    if not root or not os.path.isdir(root):
        return []

    empty = []
    empty_set = set()
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        if not filenames and all(
            os.path.join(dirpath, d) in empty_set for d in dirnames
        ):
            empty.append(dirpath)
            empty_set.add(dirpath)

    if root in empty_set:
        empty.remove(root)

    return empty


def delete_empty_folders(paths: list, log=None) -> dict:
    """Removes each folder in `paths` (expects deepest-first order, as
    returned by find_empty_folders). Skips any that fail instead of
    raising — a folder that gained a file since scanning just gets left.
    """
    summary = {"deleted": 0, "skipped": []}
    if log is None:
        log = lambda msg: None

    for path in paths:
        try:
            os.rmdir(path)
            summary["deleted"] += 1
        except OSError:
            summary["skipped"].append(path)

    if summary["skipped"]:
        log(f"{len(summary['skipped'])} folder(s) could not be removed (no longer empty or in use)")

    return summary


def analyze_folder(root: str) -> list:
    """One-level-deep breakdown of what's using space inside `root`.
    Returns a list of dicts sorted by size descending:
    {"name", "path", "size", "is_dir"}
    """
    results = []
    if not root or not os.path.isdir(root):
        return results

    for entry in os.listdir(root):
        full = os.path.join(root, entry)
        try:
            if os.path.islink(full):
                continue
            if os.path.isdir(full):
                results.append({
                    "name": entry, "path": full,
                    "size": get_dir_size(full), "is_dir": True,
                })
            elif os.path.isfile(full):
                results.append({
                    "name": entry, "path": full,
                    "size": os.path.getsize(full), "is_dir": False,
                })
        except OSError:
            continue

    results.sort(key=lambda x: x["size"], reverse=True)
    return results


def reset_icon_cache(log=None) -> bool:
    """Clears Windows' icon cache database and restarts Explorer so
    icons redraw fresh. Fixes blank/wrong icon glitches. Explorer is
    always restarted, even if the cache files couldn't be removed.
    """
    if log is None:
        log = lambda msg: None

    if not is_windows():
        log("Icon cache reset is only available on Windows.")
        return False

    localapp = os.environ.get("LOCALAPPDATA", "")
    removed = 0
    try:
        subprocess.run(["taskkill", "/F", "/IM", "explorer.exe"], capture_output=True, timeout=15)

        candidates = []
        old_style = os.path.join(localapp, "IconCache.db")
        if os.path.exists(old_style):
            candidates.append(old_style)

        explorer_dir = os.path.join(localapp, "Microsoft", "Windows", "Explorer")
        if os.path.isdir(explorer_dir):
            candidates.extend(glob.glob(os.path.join(explorer_dir, "iconcache_*.db")))

        for f in candidates:
            try:
                os.remove(f)
                removed += 1
            except OSError:
                pass

        log(f"Icon cache reset: {removed} file(s) removed.")
        return True
    except Exception as e:
        log(f"Icon cache reset failed: {e}")
        return False
    finally:
        # Always try to bring Explorer back, whatever else happened.
        try:
            subprocess.Popen(["explorer.exe"])
        except Exception:
            log("Could not restart Explorer automatically — please open Task Manager and start it manually (File > Run new task > explorer.exe).")
