"""
browser_core.py
----------------
Browser-related cleanup: browsing history only (never cookies, never
passwords, never login sessions). Also DNS cache flush, which is an
OS-level network fix, not really "browser" data, but grouped here.

IMPORTANT SAFETY NOTE:
History and Cookies live in the SAME SQLite database file per browser
profile ("History" and "Cookies" files). We only ever touch the
"History" file, and we NEVER open/modify the "Cookies" or "Login Data"
files. This guarantees no site logout and no password loss, by
construction rather than by being careful.
"""

import os
import sqlite3
import shutil
import subprocess
import tempfile


def is_windows() -> bool:
    return os.name == "nt"


def _list_profile_dirs(user_data_dir: str) -> list:
    """Returns profile folder names directly under a Chrome/Edge "User
    Data" directory: "Default" plus any "Profile 1", "Profile 2", etc.
    A folder only counts as a real profile if it has a "Preferences"
    file (every genuine profile has one) — this filters out sibling
    folders under "User Data" that aren't profiles, like "Crashpad",
    "ShaderCache", or "System Profile".

    Sorted with "Default" first, then Profile N in numeric order, so
    results are stable and predictable rather than OS-listing order.
    """
    if not os.path.isdir(user_data_dir):
        return []

    def sort_key(name):
        if name == "Default":
            return (0, 0)
        try:
            return (1, int(name.split(" ", 1)[1]))
        except (IndexError, ValueError):
            return (2, name)

    found = []
    try:
        for entry in os.listdir(user_data_dir):
            if entry != "Default" and not entry.startswith("Profile "):
                continue
            full = os.path.join(user_data_dir, entry)
            if os.path.isdir(full) and os.path.isfile(os.path.join(full, "Preferences")):
                found.append(entry)
    except OSError:
        return []
    found.sort(key=sort_key)
    return found


def _browser_profiles():
    """Returns {display_label: (browser_name, profile_dir)} for every
    browser profile found on this machine — including secondary
    profiles (Profile 1, Profile 2, ...), not just Default.

    browser_name ("Chrome"/"Edge") is kept separate from the display
    label ("Chrome (Profile 1)") because callers need the plain browser
    name to check whether that browser's process is running.

    Internal implementation — use get_browser_profiles() from outside
    this module.
    """
    localapp = os.environ.get("LOCALAPPDATA", "")
    profiles = {}
    if not localapp:
        return profiles

    browser_paths = {
        "Chrome": os.path.join(localapp, "Google", "Chrome", "User Data"),
        "Edge": os.path.join(localapp, "Microsoft", "Edge", "User Data"),
    }
    for browser_name, user_data_dir in browser_paths.items():
        for profile_name in _list_profile_dirs(user_data_dir):
            label = f"{browser_name} ({profile_name})"
            profiles[label] = (browser_name, os.path.join(user_data_dir, profile_name))

    return profiles


def get_browser_profiles():
    """Public API: returns {display_label: (browser_name, profile_dir)}
    for every browser profile found on this machine.
    Delegates to _browser_profiles(); callers outside this module should
    use this function rather than the private one.
    """
    return _browser_profiles()


def is_browser_running(browser_name: str) -> bool:
    """Checks if a browser process is currently running (Windows only).
    History DB files are locked while the browser is open, so callers
    should check this before attempting to clear history.
    """
    if not is_windows():
        return False
    process_map = {"Chrome": "chrome.exe", "Edge": "msedge.exe"}
    exe = process_map.get(browser_name)
    if not exe:
        return False
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {exe}"],
            capture_output=True, text=True, timeout=10,
        )
        return exe.lower() in result.stdout.lower()
    except Exception:
        # If we can't check, assume it might be running — safer to skip.
        return True


def get_history_entry_count(profile_dir: str) -> int:
    """Counts rows in the History file's `urls` table, without modifying
    anything. Returns 0 if the file is missing, locked, or malformed.
    """
    history_file = os.path.join(profile_dir, "History")
    if not os.path.exists(history_file):
        return 0
    return _read_only_query(history_file, "SELECT COUNT(*) FROM urls")


def clear_browsing_history(profile_dir: str, log=None) -> bool:
    """Deletes all rows from the History file's `urls` and `visits` tables.
    Never touches Cookies or Login Data — those are separate files this
    function never opens.

    Works on a temporary COPY of the History file, then swaps it in —
    so a crash mid-operation can't corrupt the original.
    """
    if log is None:
        log = lambda msg: None

    history_file = os.path.join(profile_dir, "History")
    if not os.path.exists(history_file):
        log("No history file found — nothing to clear.")
        return True

    tmp_copy = None
    try:
        fd, tmp_copy = tempfile.mkstemp(suffix=".sqlite")
        os.close(fd)
        shutil.copy2(history_file, tmp_copy)
        # Chrome's History file may be in WAL mode with pending data in a
        # companion -wal file. Copy it too if present, so we don't lose
        # recent entries that haven't been checkpointed into the main file.
        for suffix in ("-wal", "-shm"):
            companion = history_file + suffix
            if os.path.exists(companion):
                shutil.copy2(companion, tmp_copy + suffix)

        conn = sqlite3.connect(tmp_copy)
        try:
            cur = conn.cursor()
            # Force rollback-journal mode: this merges any WAL data into
            # the main file immediately, so our writes below are
            # guaranteed to end up in tmp_copy itself (not a stray -wal
            # file we'd forget to copy back).
            cur.execute("PRAGMA journal_mode=DELETE")
            cur.execute("DELETE FROM visits")
            cur.execute("DELETE FROM urls")
            conn.commit()
        finally:
            conn.close()

        shutil.copy2(tmp_copy, history_file)

        # The replacement we just wrote is guaranteed non-WAL (we forced
        # journal_mode=DELETE above), so it's fully self-contained. Any
        # -wal/-shm files still sitting next to the ORIGINAL history_file
        # at this point are now stale leftovers from before the clear —
        # and leaving them isn't just untidy: a stale -wal file replays
        # its old frames on top of whatever main file it finds next time
        # anything opens this database, which can literally bring back
        # the rows we just deleted. Remove them so the clear actually
        # sticks.
        for suffix in ("-wal", "-shm"):
            stale = history_file + suffix
            if os.path.exists(stale):
                try:
                    os.remove(stale)
                except OSError:
                    pass

        log("Browsing history cleared.")
        return True
    except sqlite3.OperationalError as e:
        log(f"Could not clear history — is the browser still open? ({e})")
        return False
    except OSError as e:
        log(f"Could not clear history: {e}")
        return False
    finally:
        if tmp_copy:
            for path in (tmp_copy, tmp_copy + "-wal", tmp_copy + "-shm"):
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass


def _read_only_query(db_file: str, query: str):
    """Runs a read-only query against a (possibly locked) SQLite file by
    querying a temp copy, so we never risk writing to the live file.
    """
    tmp_copy = None
    try:
        fd, tmp_copy = tempfile.mkstemp(suffix=".sqlite")
        os.close(fd)
        shutil.copy2(db_file, tmp_copy)
        conn = sqlite3.connect(tmp_copy)
        try:
            cur = conn.cursor()
            cur.execute(query)
            row = cur.fetchone()
            return row[0] if row else 0
        finally:
            conn.close()
    except Exception:
        return 0
    finally:
        if tmp_copy and os.path.exists(tmp_copy):
            try:
                os.remove(tmp_copy)
            except OSError:
                pass


def flush_dns(log=None) -> bool:
    """Runs `ipconfig /flushdns`. Safe, reversible (cache just rebuilds)."""
    if log is None:
        log = lambda msg: None
    if not is_windows():
        log("DNS flush is only available on Windows.")
        return False
    try:
        result = subprocess.run(
            ["ipconfig", "/flushdns"], capture_output=True, text=True, timeout=15
        )
        log(result.stdout.strip() or "DNS cache flushed.")
        return result.returncode == 0
    except Exception as e:
        log(f"DNS flush failed: {e}")
        return False
