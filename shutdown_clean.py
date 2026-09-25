"""
shutdown_clean.py
-----------------
Silent, headless cleaner that runs automatically when Windows shuts down.

This script is registered as a Group Policy Shutdown Script via
`shutdown_setup.py` (or the PC Cleaner GUI "Shutdown Clean" button).

How it works
------------
Windows Group Policy Shutdown Scripts run BEFORE the session is torn down,
and Windows WAITS for the script to finish before continuing the shutdown
sequence.  This guarantees a complete clean on every shutdown — no race
condition, no partial run.

Fast Startup warning
--------------------
Windows "Fast Startup" (hybrid shutdown) does NOT trigger a real shutdown —
it hibernates the kernel instead.  Group Policy shutdown scripts are skipped
in this mode.  shutdown_setup.py disables Fast Startup so that every "Shut
Down" from the Start menu triggers a real shutdown and this script always runs.

Log files
---------
Text log:  %LOCALAPPDATA%\\PCCleaner\\shutdown_clean.log
Structured errors (if any): %LOCALAPPDATA%\\PCCleaner\\error_log.json
    (same file the GUI's "Error Log" viewer reads — see error_log.py)
Results are also appended into the normal PC Cleaner history, shared
with the GUI.

Design principles
-----------------
- No GUI, no popups, no console window (run via pythonw.exe).
- Never raises an unhandled exception — any error is written to the log.
- Cleans only "safe"-badge categories by default (same set as Quick Clean).
- Runs as the logged-on user, so only user-level paths are cleaned unless
  the script is elevated (see shutdown_setup.py for elevation option).
"""

import os
import sys
import logging
from datetime import datetime

# ---------------------------------------------------------------------------
# Bootstrap: make sure the script can find its siblings whether it is run
# directly, via pythonw, or via Group Policy (which sets CWD to System32).
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import cleaner_core
import history_log
import error_log


# ---------------------------------------------------------------------------
# Logging — dual output: rotating log file + Python logging
# ---------------------------------------------------------------------------
def _setup_log() -> logging.Logger:
    log_dir = os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
        "PCCleaner",
    )
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "shutdown_clean.log")

    logger = logging.getLogger("shutdown_clean")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)s  %(message)s"))
        logger.addHandler(fh)
    return logger, log_path


# ---------------------------------------------------------------------------
# Category selection for shutdown clean
# ---------------------------------------------------------------------------
# These are the category IDs that will be cleaned on every shutdown.
# Only "safe"-badge categories are included — nothing that needs a service
# stop or could affect the next boot if partially cleaned.
#
# Windows Update categories (windows_update_cache, delivery_optimization)
# no longer exist in cleaner_core.build_categories() at all — Windows
# Update is permanently disabled at the OS level on this machine (see
# disable_windows_update.reg/.bat), so those categories were removed
# there rather than merely excluded here.
_SHUTDOWN_CLEAN_IDS = {
    "user_temp",
    "windows_temp",
    "chrome_cache",
    "edge_cache",
    "thumbnail_cache",
    "wer_reports",
    "recycle_bin",
}


def _should_clean(cat: dict) -> bool:
    """Return True if this category should be cleaned at shutdown."""
    if cat["id"] not in _SHUTDOWN_CLEAN_IDS:
        return False
    # Skip categories that need admin if we're not running elevated.
    return not cat.get("needs_admin") or cleaner_core.is_admin()


# ---------------------------------------------------------------------------
# Main clean routine
# ---------------------------------------------------------------------------
def run_shutdown_clean(logger: logging.Logger) -> dict:
    """Run the shutdown clean and return a result summary dict."""
    categories = cleaner_core.build_categories()
    total_freed = 0
    cleaned_ids = []
    errors = []

    logger.info("=== Shutdown clean started ===")

    for cat in categories:
        if not _should_clean(cat):
            continue

        cat_name = cat["name"]

        # Recycle Bin is a special case — handled by Shell API, not path.
        if cat.get("special") == "recycle_bin":
            try:
                freed = cleaner_core.get_recycle_bin_size()
                if cleaner_core.empty_recycle_bin():
                    total_freed += freed
                    cleaned_ids.append(cat["id"])
                    logger.info(f"  {cat_name}: emptied ({cleaner_core.format_size(freed)})")
                else:
                    logger.warning(f"  {cat_name}: empty_recycle_bin() returned False")
            except Exception as exc:
                msg = f"{cat_name}: {exc}"
                logger.error(msg)
                errors.append(msg)
                error_log.record(f"shutdown_clean:{cat['id']}", exc)
            continue

        # Normal path-based categories.
        cat_freed = 0
        file_filter = cat.get("file_filter")

        for path in cat.get("paths", []):
            if not path:
                continue
            try:
                summary = cleaner_core.delete_dir_contents(
                    path,
                    log=lambda m: logger.info(f"    {m}"),
                    file_filter=file_filter,
                )
                cat_freed += summary["deleted_bytes"]
                if summary["skipped"]:
                    logger.info(
                        f"    {len(summary['skipped'])} file(s) skipped (in use — normal)"
                    )
            except Exception as exc:
                msg = f"{cat_name} ({path}): {exc}"
                logger.error(msg)
                errors.append(msg)
                error_log.record(f"shutdown_clean:{cat['id']}", exc)

        total_freed += cat_freed
        cleaned_ids.append(cat["id"])
        logger.info(f"  {cat_name}: freed {cleaner_core.format_size(cat_freed)}")

    logger.info(
        f"=== Shutdown clean done — total freed: {cleaner_core.format_size(total_freed)} ==="
    )

    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "categories": cleaned_ids,
        "bytes_freed": total_freed,
        "mode": "shutdown",
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    logger, log_path = _setup_log()
    try:
        result = run_shutdown_clean(logger)
        # Write into the shared GUI history so the user can see it.
        history_log.log_cleanup(result)
    except Exception as exc:
        # Last-resort catch — we must never crash during Windows shutdown.
        try:
            logger.critical(f"Unhandled exception in shutdown_clean: {exc}", exc_info=True)
        except Exception:
            pass  # Even the logger failed — nothing more we can do.
        try:
            error_log.record("shutdown_clean_fatal", exc)
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
