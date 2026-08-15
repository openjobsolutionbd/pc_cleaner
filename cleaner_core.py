"""
cleaner_core.py
----------------
Platform-agnostic core logic for the PC Cleaner app:
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


def delete_dir_contents(path: str, log=None, file_filter=None) -> dict:
    """Delete everything INSIDE `path`, but keep `path` itself.

    This is the safety-critical function: it must never delete the
    category's root folder (e.g. never delete the Temp folder itself,
    only what's inside it), and it must never raise on a locked file —
    it should just skip that file and keep going.

    file_filter: optional callable(filename: str) -> bool. When given,
        only files whose name satisfies the filter are deleted; files
        that don't match are silently skipped (not counted as skipped).
        Subdirectories are also skipped entirely when a filter is active,
        because the filter is defined per filename and a directory has no
        meaningful single filename to test against. This is intentional
        for categories like Thumbnail Cache where only specific *.db
        files should be removed and the rest of the folder left intact.

    Symlinks (both file-symlinks and dir-symlinks) are always skipped —
    deleting a symlink target could break other applications that depend
    on it, so we never touch them even when they appear inside a temp
    folder.

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

        # Never follow or delete symlinks — file or directory.
        if os.path.islink(full):
            continue

        try:
            if os.path.isdir(full):
                # When a filter is active we only remove individual files
                # that match it, so skip subdirectories entirely.
                if file_filter is not None:
                    continue
                size_before = get_dir_size(full)
                shutil.rmtree(full)
                summary["deleted_bytes"] += size_before
                summary["deleted_dirs"] += 1
            else:
                # Apply the per-filename filter if one was provided.
                if file_filter is not None and not file_filter(entry):
                    continue
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


def stop_windows_update_service(log=None) -> str:
    """Attempts to stop the Windows Update service (wuauserv).

    Returns one of three string tokens so callers can act correctly:

      "stopped"         — service was running and we stopped it;
                          caller should restart it after cleanup.
      "already_stopped" — service was not running to begin with;
                          cleanup is safe to proceed, no restart needed.
      "failed"          — service is running but we could not stop it;
                          caller should skip this category entirely to
                          avoid corrupting a partially-written cache.

    'net stop' exit code 2 with the "not started" message means the
    service is already down — this is treated as safe, not as an error,
    because deleting the cache while the service is stopped is exactly
    what we want regardless of who stopped it.
    """
    if log is None:
        log = lambda msg: None
    if not is_windows():
        return "already_stopped"
    try:
        result = subprocess.run(["net", "stop", "wuauserv"], capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return "stopped"
        # "The service has not been started." — service already down, safe to proceed.
        combined = (result.stderr + result.stdout).lower()
        if "not been started" in combined or "not started" in combined:
            return "already_stopped"
        log(f"Could not stop Windows Update service: {result.stderr.strip() or result.stdout.strip()}")
        return "failed"
    except Exception as e:
        log(f"Could not stop Windows Update service: {e}")
        return "failed"


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
        # NOTE: "Windows Update Old Files" and "Delivery Optimization Files"
        # categories were removed here. This machine has Windows Update
        # permanently disabled at the OS level (see disable_windows_update.reg
        # / .bat), so wuauserv is set to Disabled — meaning every single
        # cleaning run would call stop_windows_update_service(), always get
        # "failed" back (a disabled service can't be stopped), and log a
        # confusing "Could not stop Windows Update service" message despite
        # nothing being wrong. Removing the category entirely avoids both
        # the pointless service-control code path and that misleading log
        # noise. stop_windows_update_service()/start_windows_update_service()
        # are left in place below in case Windows Update is ever re-enabled.
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
