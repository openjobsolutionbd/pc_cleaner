"""
scheduler.py
------------
Creates/removes a Windows scheduled task that runs this app with
`--auto-clean` on a recurring basis, using the built-in `schtasks`
command (no extra dependency needed).
"""

import os
import sys
import subprocess

TASK_NAME = "WindowsCleanerAutoClean"


def is_windows() -> bool:
    return os.name == "nt"


def build_run_command(auto_clean_flag: str = "--auto-clean") -> str:
    """Builds the exact command the scheduled task should run — correct
    both for a built .exe and for running straight from source (e.g.
    testing before build_exe.bat has been run).

    A built .exe (`sys.frozen` is True) can be launched directly.
    A .py file CANNOT: Task Scheduler doesn't reliably execute .py
    files as programs (that relies on a file-type association that
    may not resolve the same way in the Task Scheduler context, and
    typically doesn't forward extra arguments like --auto-clean
    correctly even when it does resolve). So when unfrozen, the
    Python interpreter (sys.executable) is invoked explicitly with the
    script path as an argument, instead of trying to run the .py file
    as if it were the program.
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" {auto_clean_flag}'
    script_path = os.path.abspath(sys.argv[0])
    return f'"{sys.executable}" "{script_path}" {auto_clean_flag}'


def create_scheduled_task(run_command: str, frequency: str = "WEEKLY",
                           day: str = "SUN", time: str = "03:00", log=None) -> bool:
    """run_command: the full command to run, e.g. from build_run_command().
    frequency: 'DAILY' or 'WEEKLY'. day is only used for WEEKLY (e.g. 'SUN', 'MON')."""
    if log is None:
        log = lambda msg: None
    if not is_windows():
        log("Scheduling is only available on Windows.")
        return False

    cmd = [
        "schtasks", "/Create",
        "/SC", frequency,
        "/TN", TASK_NAME,
        "/TR", run_command,
        "/ST", time,
        "/F",  # overwrite if it already exists
    ]
    if frequency.upper() == "WEEKLY":
        cmd += ["/D", day]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            log(f"Scheduled: runs {frequency.lower()} at {time}.")
            return True
        log(f"Could not create schedule: {result.stderr.strip()}")
        return False
    except Exception as e:
        log(f"Could not create schedule: {e}")
        return False


def remove_scheduled_task(log=None) -> bool:
    if log is None:
        log = lambda msg: None
    if not is_windows():
        log("Scheduling is only available on Windows.")
        return False
    try:
        result = subprocess.run(
            ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            return True
        log(f"Could not remove schedule: {result.stderr.strip()}")
        return False
    except Exception as e:
        log(f"Could not remove schedule: {e}")
        return False


def is_task_scheduled() -> bool:
    if not is_windows():
        return False
    try:
        result = subprocess.run(
            ["schtasks", "/Query", "/TN", TASK_NAME],
            capture_output=True, text=True, timeout=15,
        )
        return result.returncode == 0
    except Exception:
        return False
