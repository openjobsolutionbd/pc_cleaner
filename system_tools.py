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


# ---------------------------------------------------------------------------
# Root / critical-folder protection
# ---------------------------------------------------------------------------
#
# find_empty_folders / delete_empty_folders / analyze_folder operate on
# whatever folder the USER picks via a folder-picker dialog in the GUI —
# unlike cleaner_core.py's categories, these paths are not hardcoded, so
# they need their own guard here rather than relying on the GUI to never
# offer a dangerous choice.
#
# is_protected_root() rejects:
#   - a drive root itself ("C:\", "C:/", "/")
#   - well-known critical OS/user folders, matched exactly (not just a
#     prefix check) so a *subfolder* of e.g. Documents is still allowed —
#     only the critical folder itself is blocked.

_PROTECTED_FOLDER_NAMES = {
    "windows", "program files", "program files (x86)", "programdata",
    "users", "system32", "syswow64", "boot", "recovery",
    "windows.old", "$recycle.bin", "perflogs",
}

_PROTECTED_USER_FOLDER_NAMES = {
    "documents", "desktop", "pictures", "downloads", "videos", "music",
    "onedrive", "appdata",
}


def is_drive_root(path: str) -> bool:
    """True for "C:\\", "C:/", "D:\\", or POSIX "/" (used in tests).

    Deliberately checks the raw string rather than relying on
    os.path.splitdrive/ntpath, because this app must recognize Windows
    drive letters correctly even in a Linux dev/test sandbox where
    ntpath-specific parsing isn't the default — the app itself only
    ever runs on Windows, but its safety checks are unit-tested here.
    """
    if not path:
        return False
    p = path.strip()
    if p in ("/", "\\"):
        return True
    # Windows drive root: exactly "X:", "X:\", or "X:/"
    if len(p) >= 2 and p[1] == ":" and p[0].isalpha():
        rest = p[2:]
        return rest in ("", "\\", "/")
    return False


def _split_path_parts(path: str) -> list:
    """Splits a path into its component folder names, accepting both
    "\\" and "/" as separators regardless of the current OS — needed
    because these Windows-style paths are also exercised by unit tests
    running on Linux, where os.path wouldn't treat "\\" as a separator.
    """
    normalized = path.replace("\\", "/")
    return [part for part in normalized.split("/") if part]


def is_protected_root(path: str) -> bool:
    """True if `path` is a drive root or a well-known critical folder that
    should never be scanned/emptied/deleted as a whole — e.g. the user's
    own Documents folder, or C:\\Windows.

    A SUBFOLDER of a protected folder (e.g. "C:\\Users\\Me\\Documents\\Old")
    is NOT protected by this check — only the critical folder itself is.
    This matches the app's guarantee ("root folders/drives are never
    deleted") without also blocking legitimate cleanup inside e.g.
    Downloads or a user's home directory.
    """
    if not path:
        return True  # empty/None path is never safe to act on

    if is_drive_root(path):
        return True

    parts = _split_path_parts(path)
    if not parts:
        return True

    base = parts[-1].lower()

    if base in _PROTECTED_FOLDER_NAMES:
        return True

    # User-profile-level folders like Documents/Desktop/Downloads are only
    # protected when they sit directly under a user's home folder
    # (…\Users\<name>\Documents), not if some other folder happens to
    # share that name deeper in a path.
    if base in _PROTECTED_USER_FOLDER_NAMES:
        parent = parts[-2].lower() if len(parts) >= 2 else ""
        grandparent = parts[-3].lower() if len(parts) >= 3 else ""
        if parent == "users" or grandparent == "users":
            return True

    return False


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

    Refuses to scan a drive root or a critical system/user folder
    (e.g. "C:\\", "C:\\Windows", "C:\\Users\\Me\\Documents") — returns []
    immediately instead, so nothing inside one can ever be listed as
    "safe to delete" in the first place.
    """
    if not root or not os.path.isdir(root):
        return []
    if is_protected_root(root):
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

    Safety: re-checks is_protected_root() on every path immediately
    before removing it, even though find_empty_folders already filtered
    the root. This is a deliberate second, independent check right at
    the point of deletion — so even if `paths` came from somewhere else,
    or the list was edited between scan and delete, a protected folder
    still can never be removed here.
    """
    summary = {"deleted": 0, "skipped": []}
    if log is None:
        log = lambda msg: None

    for path in paths:
        if is_protected_root(path):
            summary["skipped"].append(path)
            log(f"Refused to delete protected folder: {path}")
            continue
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

    Refuses to analyze a drive root directly (e.g. "C:\\") — this is a
    read-only function so there's no deletion risk, but a full drive-root
    scan is slow, not useful (thousands of system files), and any
    "select all + delete" flow built on top of this should not have a
    drive root in its results to begin with. Critical named folders like
    Windows or Documents ARE still analyzable (read-only, non-destructive)
    since seeing what's inside them is legitimate and useful.
    """
    results = []
    if not root or not os.path.isdir(root):
        return results
    if is_drive_root(root):
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
