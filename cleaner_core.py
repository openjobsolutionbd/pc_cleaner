"""
cleaner_core.py
----------------
Platform-agnostic core logic for the Windows Cleaner app:
- calculating folder sizes
- deleting folder *contents* (never the folder itself)
- formatting byte sizes
- the list of "junk" categories and where they live on a Windows machine

This file has NO Tkinter / GUI code and NO code that only runs on Windows,
except where explicitly guarded by `if os.name == "nt"`. That's what makes
it possible to unit-test the risky parts (deletion) on any OS.
"""

import os
import shutil
import ctypes
import subprocess


# ---------------------------------------------------------------------------
# Basic helpers
# ---------------------------------------------------------------------------

def format_size(num_bytes: int) -> str:
    """Human readable size, Bengali-friendly units (KB/MB/GB same as Windows)."""
    if num_bytes < 0:
        num_bytes = 0
    step = 1024.0
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num_bytes < step:
            return f"{num_bytes:.1f} {unit}" if unit != "B" else f"{int(num_bytes)} {unit}"
        num_bytes /= step
    return f"{num_bytes:.1f} PB"


def get_dir_size(path: str) -> int:
    """Recursively sum the size of every file under `path`.
    Never raises: unreadable/locked files are simply skipped (counted as 0).
    Returns 0 if the path doesn't exist.
    """
    if not path or not os.path.isdir(path):
        return 0

    total = 0
    for root, dirs, files in os.walk(path, onerror=lambda e: None):
        for name in files:
            fpath = os.path.join(root, name)
            try:
                if not os.path.islink(fpath):
                    total += os.path.getsize(fpath)
            except OSError:
                # File vanished, or permission denied — skip, don't crash.
                continue
    return total


def delete_dir_contents(path: str, log=None) -> dict:
    """Delete everything INSIDE `path`, but keep `path` itself.

    This is the safety-critical function: it must never delete the
    category's root folder (e.g. never delete the Temp folder itself,
    only what's inside it), and it must never raise on a locked file —
    it should just skip that file and keep going.

    Returns a summary dict: {"deleted_bytes", "deleted_files",
    "deleted_dirs", "skipped": [list of paths that could not be removed]}.
    """
    summary = {"deleted_bytes": 0, "deleted_files": 0, "deleted_dirs": 0, "skipped": []}
    if log is None:
        log = lambda msg: None

    if not path or not os.path.isdir(path):
        log(f"Path not found, skipping: {path}")
        return summary

    for entry in os.listdir(path):
        full = os.path.join(path, entry)
        try:
            if os.path.isdir(full) and not os.path.islink(full):
                size_before = get_dir_size(full)
                shutil.rmtree(full)
                summary["deleted_bytes"] += size_before
                summary["deleted_dirs"] += 1
            else:
                size_before = os.path.getsize(full) if os.path.exists(full) else 0
                os.remove(full)
                summary["deleted_bytes"] += size_before
                summary["deleted_files"] += 1
        except OSError:
            # File is in use / permission denied — normal and expected for
            # some temp files. Skip it, don't stop the whole cleanup.
            summary["skipped"].append(full)
            continue

    if summary["skipped"]:
        log(f"{len(summary['skipped'])} file(s)/folder(s) skipped because they were in use (normal)")

    return summary


# ---------------------------------------------------------------------------
# Windows-only helpers (Recycle Bin, admin check, service stop)
# ---------------------------------------------------------------------------

def is_windows() -> bool:
    return os.name == "nt"


def is_admin() -> bool:
    if not is_windows():
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def get_recycle_bin_size() -> int:
    """Uses the Windows Shell API to get the real Recycle Bin size in bytes."""
    if not is_windows():
        return 0

    class SHQUERYRBINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_uint32),
            ("i64Size", ctypes.c_int64),
            ("i64NumItems", ctypes.c_int64),
        ]

    info = SHQUERYRBINFO()
    info.cbSize = ctypes.sizeof(SHQUERYRBINFO)
    try:
        ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info))
        return max(0, info.i64Size)
    except Exception:
        return 0


def empty_recycle_bin() -> bool:
    if not is_windows():
        return False
    SHERB_NOCONFIRMATION = 0x00000001
    SHERB_NOPROGRESSUI = 0x00000002
    SHERB_NOSOUND = 0x00000004
    try:
        ctypes.windll.shell32.SHEmptyRecycleBinW(
            None, None, SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND
        )
        return True
    except Exception:
        return False


def stop_windows_update_service(log=None) -> bool:
    if log is None:
        log = lambda msg: None
    if not is_windows():
        return False
    try:
        result = subprocess.run(["net", "stop", "wuauserv"], capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return True
        log(f"Could not stop Windows Update service: {result.stderr.strip() or result.stdout.strip()}")
        return False
    except Exception as e:
        log(f"Could not stop Windows Update service: {e}")
        return False


def start_windows_update_service(log=None) -> bool:
    if log is None:
        log = lambda msg: None
    if not is_windows():
        return False
    try:
        result = subprocess.run(["net", "start", "wuauserv"], capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return True
        log(f"Could not start Windows Update service: {result.stderr.strip() or result.stdout.strip()}")
        return False
    except Exception as e:
        log(f"Could not start Windows Update service: {e}")
        return False


# ---------------------------------------------------------------------------
# Category definitions
# ---------------------------------------------------------------------------

def _env(name, default=""):
    return os.environ.get(name, default)


def build_categories():
    """Returns the list of cleanable categories, with paths resolved for the
    current machine. Safe to call on any OS (paths just won't exist on
    non-Windows, so scanned size will be 0).
    """
    windir = _env("WINDIR", "C:\\Windows")
    localapp = _env("LOCALAPPDATA", "")
    temp = _env("TEMP", "")

    categories = [
        {
            "id": "user_temp",
            "name": "User Temp Files",
            "desc": "Temporary files created by programs. Builds up constantly.",
            "paths": [temp] if temp else [],
            "needs_admin": False,
            "default_checked": True,
            "badge": "safe",
        },
        {
            "id": "windows_temp",
            "name": "Windows Temp Files",
            "desc": "System-level temp files. Safe to delete.",
            "paths": [os.path.join(windir, "Temp")] if windir else [],
            "needs_admin": True,
            "default_checked": True,
            "badge": "safe",
        },
        {
            "id": "chrome_cache",
            "name": "Chrome Browser Cache",
            "desc": "Temporary copies of website files/images. Sites may load slightly slower the first time after clearing.",
            "paths": [
                os.path.join(localapp, "Google", "Chrome", "User Data", "Default", "Cache")
            ] if localapp else [],
            "needs_admin": False,
            "default_checked": True,
            "badge": "safe",
        },
        {
            "id": "edge_cache",
            "name": "Edge Browser Cache",
            "desc": "Microsoft Edge's temporary browsing files.",
            "paths": [
                os.path.join(localapp, "Microsoft", "Edge", "User Data", "Default", "Cache")
            ] if localapp else [],
            "needs_admin": False,
            "default_checked": True,
            "badge": "safe",
        },
        {
            "id": "thumbnail_cache",
            "name": "Thumbnail Cache",
            "desc": "Preview images for photos/videos in folders. Regenerates automatically.",
            "paths": [
                os.path.join(localapp, "Microsoft", "Windows", "Explorer")
            ] if localapp else [],
            "needs_admin": False,
            "default_checked": True,
            "badge": "safe",
            "file_filter": lambda name: name.lower().startswith("thumbcache_"),
        },
        {
            "id": "wer_reports",
            "name": "Error Report Files",
            "desc": "Crash reports saved for diagnostics only.",
            "paths": [
                os.path.join(localapp, "Microsoft", "Windows", "WER")
            ] if localapp else [],
            "needs_admin": False,
            "default_checked": True,
            "badge": "safe",
        },
        {
            "id": "windows_update_cache",
            "name": "Windows Update Old Files",
            "desc": "Downloaded copies of already-installed updates. Current updates stay intact; files re-download if ever needed.",
            "paths": [os.path.join(windir, "SoftwareDistribution", "Download")] if windir else [],
            "needs_admin": True,
            "default_checked": False,
            "badge": "caution",
            "stop_service": True,
        },
        {
            "id": "delivery_optimization",
            "name": "Delivery Optimization Files",
            "desc": "Cache used for sharing updates with other devices.",
            "paths": [
                os.path.join(windir, "SoftwareDistribution", "DeliveryOptimization", "Cache")
            ] if windir else [],
            "needs_admin": True,
            "default_checked": True,
            "badge": "safe",
        },
        {
            "id": "crash_dumps",
            "name": "Crash Dump Files (Minidump)",
            "desc": "System crash diagnostic files. Safe to delete unless you're actively debugging a crash.",
            "paths": [os.path.join(windir, "Minidump")] if windir else [],
            "needs_admin": True,
            "default_checked": False,
            "badge": "caution",
        },
        {
            "id": "prefetch",
            "name": "Prefetch Files (Optional)",
            "desc": "Files Windows keeps to speed up program launches. Deleting means the first launch after may be a bit slower.",
            "paths": [os.path.join(windir, "Prefetch")] if windir else [],
            "needs_admin": True,
            "default_checked": False,
            "badge": "caution",
        },
    ]
    return categories
