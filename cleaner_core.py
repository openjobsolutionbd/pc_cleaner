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
import stat
import ctypes
import ctypes.wintypes
import subprocess

import browser_core


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


def get_dir_size(path: str, file_filter=None) -> int:
    """Recursively sum the size of every file under `path`.
    Never raises: unreadable/locked files are simply skipped (counted as 0).
    Returns 0 if the path doesn't exist.

    file_filter: optional callable(filename: str) -> bool, with exactly
        the same meaning as in delete_dir_contents(): when given, only
        files directly inside `path` whose name satisfies the filter are
        counted, and subdirectories are skipped entirely. This keeps a
        scan's size in step with what cleaning would really delete (e.g.
        the Thumbnail Cache category only removes thumbcache_* files, so
        the rest of the Explorer folder must not be counted as
        reclaimable).

    Uses os.scandir() rather than os.walk() + os.path.getsize(): os.walk()
    already uses scandir() internally, but it throws away the per-entry
    type/stat info it gathered and hands back plain filename strings, so
    calling os.path.getsize()/os.path.islink() on those triggers a second,
    redundant stat() syscall per file. Reading straight from the DirEntry
    objects instead reuses the info from the original directory listing
    wherever the OS provides it for free — a well-documented 2-20x win on
    Windows especially, which matters here since browser cache folders
    (now scanned for every profile, see _chromium_cache_paths) can easily
    contain thousands of small files.
    """
    if not path or not os.path.isdir(path):
        return 0

    total = 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if file_filter is not None:
                            continue  # mirrors delete_dir_contents
                        total += get_dir_size(entry.path)
                    else:
                        if file_filter is not None and not file_filter(entry.name):
                            continue
                        total += entry.stat(follow_symlinks=False).st_size
                except OSError:
                    # File vanished, or permission denied — skip, don't crash.
                    continue
    except OSError:
        # Directory vanished or became unreadable between the isdir()
        # check above and opening it — treat as "nothing found here".
        return total
    return total


def _is_link_or_reparse_point(entry) -> bool:
    """True for a symlink, a Windows junction, or any other reparse point.
    Used for entries *inside* a folder being cleaned: we never follow or
    delete these (same rule as the top level), because removing/entering
    one could touch whatever it points at. If the type can't be read at
    all, treat it as unsafe and leave it alone.
    """
    try:
        if entry.is_symlink():
            return True
        attrs = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
        return bool(attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except OSError:
        return True


def _remove_tree_best_effort(path: str, summary: dict) -> bool:
    """Delete `path` and everything inside it, one entry at a time, and
    NEVER stop at a file that can't be removed.

    This replaces shutil.rmtree(), which aborts the whole folder at the
    first locked/in-use file: everything it hadn't reached yet was left
    behind even though it could have been deleted, and none of the bytes
    already removed were counted. Here a locked file is recorded in
    summary["skipped"] and the loop carries on with the rest.

    Only summary["deleted_bytes"] (bytes actually removed) and
    summary["skipped"] are updated; the caller decides how to count
    this folder itself. Symlinks/junctions inside are left untouched.

    Returns True if `path` itself was removed (i.e. everything inside it
    could be removed), False if something had to be left behind.
    """
    try:
        entries = list(os.scandir(path))
    except OSError:
        summary["skipped"].append(path)
        return False

    all_gone = True
    for entry in entries:
        full = entry.path

        if _is_link_or_reparse_point(entry):
            summary["skipped"].append(full)
            all_gone = False
            continue

        try:
            is_dir = entry.is_dir(follow_symlinks=False)
        except OSError:
            summary["skipped"].append(full)
            all_gone = False
            continue

        if is_dir:
            if not _remove_tree_best_effort(full, summary):
                all_gone = False
            continue

        try:
            size = entry.stat(follow_symlinks=False).st_size
        except OSError:
            size = 0
        try:
            os.remove(full)
        except OSError:
            # In use / permission denied: skip just this file, keep going.
            summary["skipped"].append(full)
            all_gone = False
            continue
        summary["deleted_bytes"] += size

    if not all_gone:
        return False
    try:
        os.rmdir(path)
    except OSError:
        summary["skipped"].append(path)
        return False
    return True


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
    folder (this applies to symlinks/junctions nested inside
    subfolders too).

    A locked file inside a subfolder only skips THAT file: everything
    else in the subfolder is still deleted, and deleted_bytes counts
    exactly the bytes that were really removed (see
    _remove_tree_best_effort). deleted_dirs counts top-level
    subfolders that were removed completely.

    Returns a summary dict: {"deleted_bytes", "deleted_files",
    "deleted_dirs", "skipped": [list of paths that could not be removed]}.
    """
    summary = {"deleted_bytes": 0, "deleted_files": 0, "deleted_dirs": 0, "skipped": []}
    if log is None:
        log = lambda msg: None

    if not path or not os.path.isdir(path):
        log(f"Path not found, skipping: {path}")
        return summary

    # os.scandir() instead of os.listdir(): each DirEntry carries cached
    # type info from the directory listing itself, so is_symlink()/
    # is_dir() below don't need their own separate stat() syscall the way
    # os.path.islink()/os.path.isdir() on a plain filename would (see
    # get_dir_size() for the same reasoning, in more detail).
    try:
        entries = list(os.scandir(path))
    except OSError:
        log(f"Path not found, skipping: {path}")
        return summary

    for entry in entries:
        full = entry.path

        # Never follow or delete symlinks — file or directory.
        try:
            if entry.is_symlink():
                continue
        except OSError:
            continue

        try:
            if entry.is_dir(follow_symlinks=False):
                # When a filter is active we only remove individual files
                # that match it, so skip subdirectories entirely.
                if file_filter is not None:
                    continue
                if _remove_tree_best_effort(full, summary):
                    summary["deleted_dirs"] += 1
            else:
                # Apply the per-filename filter if one was provided.
                if file_filter is not None and not file_filter(entry.name):
                    continue
                try:
                    size_before = entry.stat(follow_symlinks=False).st_size
                except OSError:
                    size_before = 0
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
        is_admin_fn = ctypes.windll.shell32.IsUserAnAdmin
        is_admin_fn.argtypes = []
        is_admin_fn.restype = ctypes.wintypes.BOOL
        return bool(is_admin_fn())
    except Exception:
        return False


class _SHQUERYRBINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint32),
        ("i64Size", ctypes.c_int64),
        ("i64NumItems", ctypes.c_int64),
    ]


def get_recycle_bin_size() -> int:
    """Uses the Windows Shell API to get the real Recycle Bin size in bytes.
    Returns 0 on any failure (including off Windows) rather than raising,
    since this is only ever used to show an estimate to the user.
    """
    if not is_windows():
        return 0

    info = _SHQUERYRBINFO()
    info.cbSize = ctypes.sizeof(_SHQUERYRBINFO)
    try:
        query_fn = ctypes.windll.shell32.SHQueryRecycleBinW
        query_fn.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.POINTER(_SHQUERYRBINFO)]
        query_fn.restype = ctypes.c_long  # HRESULT
        result = query_fn(None, ctypes.byref(info))
        if result != 0:  # S_OK == 0; anything else means info wasn't filled in
            return 0
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
        empty_fn = ctypes.windll.shell32.SHEmptyRecycleBinW
        empty_fn.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.LPCWSTR, ctypes.wintypes.DWORD]
        empty_fn.restype = ctypes.c_long  # HRESULT
        empty_fn(None, None, SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND)
        # SHEmptyRecycleBinW's HRESULT is not a reliable success signal on
        # its own: it's documented to return a non-zero/error code even
        # when the Recycle Bin was already empty (a known, long-standing
        # quirk of this specific API - the PowerShell Clear-RecycleBin
        # cmdlet has the same bug reported against it). So instead of
        # trusting the return code, check the actual outcome.
        return get_recycle_bin_size() == 0
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


# Every Chromium cache folder that quietly grows over time and can drag
# a browser down — not just the main HTTP cache. Same subfolder names
# for Chrome and Edge since both are Chromium-based.
_CHROMIUM_CACHE_SUBFOLDERS = [
    "Cache",
    "Code Cache",
    "GPUCache",
    "DawnCache",
    "DawnGraphiteCache",
    os.path.join("Service Worker", "CacheStorage"),
    os.path.join("Service Worker", "ScriptCache"),
]


def _chromium_cache_paths(profiles: dict, browser_name: str) -> list:
    """Every cache subfolder, across every profile, for a Chromium-based
    browser ("Chrome" or "Edge") — not just the Default profile's main
    Cache folder. Paths that don't exist are simply skipped later by
    delete_dir_contents, so it's fine to list them speculatively.

    Takes an already-fetched profiles dict (from
    browser_core.get_browser_profiles()) rather than fetching it itself,
    so building both the Chrome and Edge cache categories together only
    scans the profile folders on disk once, not once per browser.
    """
    paths = []
    for _, (name, profile_dir) in profiles.items():
        if name != browser_name:
            continue
        for sub in _CHROMIUM_CACHE_SUBFOLDERS:
            paths.append(os.path.join(profile_dir, sub))
    return paths


def build_categories():
    """Returns the list of cleanable categories, with paths resolved for the
    current machine. Safe to call on any OS (paths just won't exist on
    non-Windows, so scanned size will be 0).
    """
    windir = _env("WINDIR", "C:\\Windows")
    localapp = _env("LOCALAPPDATA", "")
    temp = _env("TEMP", "")
    # Fetched once and reused for both the Chrome and Edge cache
    # categories below, instead of each one triggering its own full
    # profile-folder scan (get_browser_profiles() always looks at both
    # browsers regardless of which one the caller actually wants).
    browser_profiles = browser_core.get_browser_profiles() if localapp else {}

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
            "desc": "Temporary copies of website files/images, across every profile. Sites may load slightly slower the first time after clearing.",
            "paths": _chromium_cache_paths(browser_profiles, "Chrome"),
            "needs_admin": False,
            "default_checked": True,
            "badge": "safe",
        },
        {
            "id": "edge_cache",
            "name": "Edge Browser Cache",
            "desc": "Microsoft Edge's temporary browsing files, across every profile.",
            "paths": _chromium_cache_paths(browser_profiles, "Edge"),
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
