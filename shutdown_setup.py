"""
shutdown_setup.py
-----------------
Registers / removes shutdown_clean.py as a Windows Group Policy Shutdown
Script so it runs automatically every time the user shuts down the PC.

Two approaches are supported:

  Method A — Group Policy Shutdown Script (RECOMMENDED)
  -------------------------------------------------------
  Windows Group Policy allows scripts to be assigned to the "Shutdown"
  event.  Windows BLOCKS shutdown until all registered shutdown scripts
  finish, so the clean is always complete before the machine powers off.

  The script is registered by writing to:
    HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Group Policy\\Scripts
    \\Shutdown\\0\\0\\
  keys: Script  = <path to pythonw.exe>
        Parameters = "<path to shutdown_clean.py>"
        ExecTime   = ""

  This is the same registry path that gpedit.msc / Group Policy writes to
  when you add a script via Computer Configuration → Windows Settings →
  Scripts (Startup/Shutdown) → Shutdown.

  Method B — Task Scheduler on Event ID 1074 (FALLBACK)
  -------------------------------------------------------
  If Method A fails (e.g. gpedit not available on Windows Home), we fall
  back to registering a Task Scheduler task triggered by Event ID 1074
  (the "system shutdown initiated" event).  This is less reliable than
  Method A because Windows does not guarantee it will wait for the task
  to finish before completing the shutdown sequence, but it works well in
  practice for short-lived scripts like ours.

Fast Startup
------------
Windows "Fast Startup" hibernates the kernel instead of doing a real
shutdown.  Group Policy shutdown scripts are NOT run during Fast Startup.
To make the shutdown clean work reliably, Fast Startup must be disabled.
This module does that automatically by setting:
  HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Power
  HiberbootEnabled = 0
"""

import os
import sys
import winreg
import subprocess
from pathlib import Path


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE = Path(__file__).parent.resolve()
_SCRIPT = _HERE / "shutdown_clean.py"

_GPO_SHUTDOWN_KEY = (
    r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
    r"\Winlogon\GPExtensions"
)

# The actual Group Policy Scripts registry path
_GPO_SCRIPTS_BASE = (
    r"SOFTWARE\Microsoft\Windows\CurrentVersion"
    r"\Group Policy\Scripts\Shutdown\0\0"
)

_TASK_NAME = "PC_Cleaner_ShutdownClean"

_FAST_STARTUP_KEY = (
    r"SYSTEM\CurrentControlSet\Control\Session Manager\Power"
)
_FAST_STARTUP_VALUE = "HiberbootEnabled"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _pythonw() -> str:
    """Return the path to pythonw.exe next to the current Python."""
    exe = Path(sys.executable)
    pw = exe.parent / "pythonw.exe"
    if pw.exists():
        return str(pw)
    return str(exe)   # fallback — shows a console flash but still works


def _is_admin() -> bool:
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Fast Startup
# ---------------------------------------------------------------------------
def disable_fast_startup(log=None) -> bool:
    """Disable Windows Fast Startup so shutdown scripts always run.

    Sets HiberbootEnabled = 0 in the Session Manager Power registry key.
    Requires admin privileges.
    """
    if log is None:
        log = print
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            _FAST_STARTUP_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, _FAST_STARTUP_VALUE, 0, winreg.REG_DWORD, 0)
        log("Fast Startup disabled (HiberbootEnabled = 0).")
        return True
    except PermissionError:
        log("ERROR: Admin rights required to disable Fast Startup.")
        return False
    except Exception as exc:
        log(f"ERROR disabling Fast Startup: {exc}")
        return False


def enable_fast_startup(log=None) -> bool:
    """Re-enable Windows Fast Startup (restores default)."""
    if log is None:
        log = print
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            _FAST_STARTUP_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, _FAST_STARTUP_VALUE, 0, winreg.REG_DWORD, 1)
        log("Fast Startup re-enabled (HiberbootEnabled = 1).")
        return True
    except Exception as exc:
        log(f"ERROR enabling Fast Startup: {exc}")
        return False


def get_fast_startup_status() -> bool:
    """Return True if Fast Startup is currently enabled."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, _FAST_STARTUP_KEY
        ) as key:
            val, _ = winreg.QueryValueEx(key, _FAST_STARTUP_VALUE)
            return bool(val)
    except Exception:
        return False   # assume disabled if key missing


# ---------------------------------------------------------------------------
# Method A — Group Policy registry
# ---------------------------------------------------------------------------
def _register_gpo(log) -> bool:
    """Write the shutdown script entry into the Group Policy Scripts registry."""
    pythonw = _pythonw()
    params = f'"{_SCRIPT}"'
    try:
        key = winreg.CreateKeyEx(
            winreg.HKEY_LOCAL_MACHINE,
            _GPO_SCRIPTS_BASE,
            0,
            winreg.KEY_SET_VALUE,
        )
        with key:
            winreg.SetValueEx(key, "Script", 0, winreg.REG_SZ, pythonw)
            winreg.SetValueEx(key, "Parameters", 0, winreg.REG_SZ, params)
            winreg.SetValueEx(key, "ExecTime", 0, winreg.REG_BINARY, b"\x00" * 16)
        log("Registered as Group Policy Shutdown Script (Method A).")
        return True
    except PermissionError:
        log("Method A requires admin rights — trying Method B (Task Scheduler).")
        return False
    except Exception as exc:
        log(f"Method A failed ({exc}) — trying Method B.")
        return False


def _unregister_gpo(log) -> bool:
    try:
        winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, _GPO_SCRIPTS_BASE)
        log("Removed Group Policy Shutdown Script entry.")
        return True
    except FileNotFoundError:
        return True   # already gone
    except Exception as exc:
        log(f"Could not remove GPO entry: {exc}")
        return False


def _is_gpo_registered() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _GPO_SCRIPTS_BASE):
            return True
    except FileNotFoundError:
        return False


# ---------------------------------------------------------------------------
# Method B — Task Scheduler (Event ID 1074)
# ---------------------------------------------------------------------------
def _register_task(log) -> bool:
    """Register a Task Scheduler task triggered by Event ID 1074 (shutdown)."""
    pythonw = _pythonw()
    script = str(_SCRIPT)

    # schtasks /Create with an XML file gives us the most control.
    xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4"
  xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>PC Cleaner — silent clean on shutdown</Description>
  </RegistrationInfo>
  <Triggers>
    <EventTrigger>
      <Enabled>true</Enabled>
      <Subscription>
        &lt;QueryList&gt;&lt;Query Id="0" Path="System"&gt;
        &lt;Select Path="System"&gt;
          *[System[Provider[@Name='User32'] and EventID=1074]]
        &lt;/Select&gt;&lt;/Query&gt;&lt;/QueryList&gt;
      </Subscription>
    </EventTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{os.environ.get('USERNAME', 'SYSTEM')}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT5M</ExecutionTimeLimit>
    <Priority>0</Priority>
  </Settings>
  <Actions>
    <Exec>
      <Command>{pythonw}</Command>
      <Arguments>"{script}"</Arguments>
    </Exec>
  </Actions>
</Task>"""

    import tempfile
    tmp = tempfile.NamedTemporaryFile(
        suffix=".xml", mode="w", encoding="utf-16", delete=False
    )
    try:
        tmp.write(xml)
        tmp.close()
        result = subprocess.run(
            ["schtasks", "/Create", "/F", "/TN", _TASK_NAME, "/XML", tmp.name],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            log("Registered as Task Scheduler shutdown task (Method B).")
            return True
        log(f"Task Scheduler registration failed: {result.stderr.strip() or result.stdout.strip()}")
        return False
    except Exception as exc:
        log(f"Task Scheduler registration error: {exc}")
        return False
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


def _unregister_task(log) -> bool:
    try:
        result = subprocess.run(
            ["schtasks", "/Delete", "/F", "/TN", _TASK_NAME],
            capture_output=True, text=True
        )
        if result.returncode == 0 or "cannot find" in (result.stderr + result.stdout).lower():
            log("Removed Task Scheduler shutdown task.")
            return True
        log(f"Could not remove task: {result.stderr.strip()}")
        return False
    except Exception as exc:
        log(f"Error removing task: {exc}")
        return False


def _is_task_registered() -> bool:
    try:
        result = subprocess.run(
            ["schtasks", "/Query", "/TN", _TASK_NAME],
            capture_output=True, text=True
        )
        return result.returncode == 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def setup_shutdown_clean(log=None) -> bool:
    """Register shutdown_clean.py to run on every Windows shutdown.

    Steps:
      1. Disable Fast Startup (required for shutdown scripts to run).
      2. Try Group Policy registry (Method A — needs admin).
      3. Fall back to Task Scheduler Event 1074 (Method B).

    Returns True if registration succeeded by either method. Note this
    can be True even if step 1 failed — the script IS registered, but
    won't actually run on a normal shutdown until Fast Startup is off,
    so that's always logged clearly rather than being contradicted by
    an unconditional "done, this will now work" message right after it.
    """
    if log is None:
        log = print

    if not _is_admin():
        log("WARNING: Running without admin rights. Some steps may fail.")

    # Step 1: Disable Fast Startup.
    fast_startup_ok = disable_fast_startup(log)

    # Step 2: Try GPO first, fall back to schtasks.
    registered = _register_gpo(log) or _register_task(log)

    if registered and not fast_startup_ok:
        log(
            "⚠ Registered, but Fast Startup is still ON — Windows skips "
            "shutdown scripts in Fast Startup mode, so the clean will "
            "NOT actually run until this is fixed (see the warning above)."
        )

    return registered


def remove_shutdown_clean(log=None) -> bool:
    """Remove the shutdown clean registration (both methods)."""
    if log is None:
        log = print
    ok_gpo = _unregister_gpo(log)
    ok_task = _unregister_task(log)
    return ok_gpo or ok_task


def get_status() -> dict:
    """Return current registration status as a dict."""
    return {
        "gpo_registered": _is_gpo_registered(),
        "task_registered": _is_task_registered(),
        "fast_startup_disabled": not get_fast_startup_status(),
        "script_exists": _SCRIPT.exists(),
        "pythonw": _pythonw(),
    }


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "setup"
    if cmd == "setup":
        setup_shutdown_clean()
    elif cmd == "remove":
        remove_shutdown_clean()
    elif cmd == "status":
        s = get_status()
        for k, v in s.items():
            print(f"  {k}: {v}")
    else:
        print("Usage: shutdown_setup.py [setup|remove|status]")
