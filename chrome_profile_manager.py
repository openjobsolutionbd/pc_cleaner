"""
chrome_profile_manager.py
--------------------------
Opens multiple Chrome profiles safely, one at a time, throttled by
CPU/RAM so a machine with many profiles doesn't get overwhelmed. Can
also gracefully close every open Chrome window and shut the PC down
afterward.

This grew out of two standalone scripts ("Smart Chrome Profile
Opener" and "Shout Down") that used to live outside this project.
Folded in here so they share the app's testing, error-logging, and
.exe packaging instead of being separate tools a user has to keep
track of.

No third-party dependencies (matches the rest of this project):
  - CPU and RAM are read straight from the Windows API via ctypes
    (GetSystemTimes / GlobalMemoryStatusEx) instead of psutil.
  - "Is this profile already open" is checked through PowerShell's
    CIM (Get-CimInstance Win32_Process) instead of
    psutil.process_iter(). PowerShell ships with every supported
    version of Windows, so this needs nothing extra installed.
  - Chrome profile *discovery* reuses browser_core.get_browser_profiles()
    rather than re-implementing it, so both modules always agree on
    what counts as a real profile.

Nothing here ever touches the network — see test_no_network_guarantee.py.
"""

import ctypes
import ctypes.wintypes
import os
import subprocess
import time
from pathlib import Path

import browser_core


def is_windows() -> bool:
    return os.name == "nt"


# subprocess.CREATE_NO_WINDOW only exists on Windows. Resolved once at
# import time so every subprocess call below can use this unconditionally
# instead of touching the Windows-only attribute directly.
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


MAX_PROFILES_DEFAULT = 30
CPU_SAFE_DEFAULT = 60.0
RAM_SAFE_DEFAULT = 75.0
SAFE_READINGS_REQUIRED = 3
LOAD_SAMPLE_SECONDS = 1.0
MAX_WAIT_FOR_WINDOW = 60
MAX_WAIT_FOR_SAFE_LOAD = 120
MAX_WAIT_FOR_CHROME_EXIT = 60


# ----------------------------------------------------------------------
# Chrome / profile discovery
# ----------------------------------------------------------------------
def find_chrome_exe():
    """Returns a Path to chrome.exe, or None if it can't be found."""
    pf = os.environ.get("PROGRAMFILES", "")
    pfx86 = os.environ.get("PROGRAMFILES(X86)", "")
    localapp = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        Path(pf) / "Google/Chrome/Application/chrome.exe",
        Path(pfx86) / "Google/Chrome/Application/chrome.exe",
        Path(localapp) / "Google/Chrome/Application/chrome.exe",
    ]
    return next((p for p in candidates if p.exists()), None)


def list_chrome_profiles() -> list:
    """Returns Chrome profile folder names ("Default", "Profile 1", ...)
    in stable order (Default first, then numeric order). Delegates
    profile *detection* to browser_core.get_browser_profiles() so this
    module and the History-clearing feature always agree on what
    counts as a real profile — and its ordering is already correct, so
    no re-sorting is needed here.
    """
    profiles = browser_core.get_browser_profiles()
    return [
        os.path.basename(path)
        for _, (browser_name, path) in profiles.items()
        if browser_name == "Chrome"
    ]


# ----------------------------------------------------------------------
# CPU / RAM (Windows API via ctypes — no psutil)
# ----------------------------------------------------------------------
class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def ram_percent() -> float:
    """Current system-wide RAM usage, 0-100. Returns 0.0 off Windows or
    if the call fails, so callers never block on this."""
    if not is_windows():
        return 0.0
    try:
        fn = ctypes.windll.kernel32.GlobalMemoryStatusEx
        fn.argtypes = [ctypes.POINTER(_MEMORYSTATUSEX)]
        fn.restype = ctypes.wintypes.BOOL
        stat = _MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
        if not fn(ctypes.byref(stat)):
            return 0.0
        return float(stat.dwMemoryLoad)
    except Exception:
        return 0.0


class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", ctypes.c_ulong), ("dwHighDateTime", ctypes.c_ulong)]


def _filetime_to_int(ft) -> int:
    return (ft.dwHighDateTime << 32) | ft.dwLowDateTime


def _system_times():
    fn = ctypes.windll.kernel32.GetSystemTimes
    fn.argtypes = [ctypes.POINTER(_FILETIME)] * 3
    fn.restype = ctypes.wintypes.BOOL
    idle, kernel, user = _FILETIME(), _FILETIME(), _FILETIME()
    if not fn(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
        raise ctypes.WinError()
    return _filetime_to_int(idle), _filetime_to_int(kernel), _filetime_to_int(user)


def cpu_percent(sample_seconds: float = LOAD_SAMPLE_SECONDS) -> float:
    """Current system-wide CPU usage, 0-100, measured over
    sample_seconds (this blocks for that long — always call from a
    background thread, never the GUI thread).

    Two samples of idle/kernel/user time, sample_seconds apart. Note
    Windows' kernel time already includes idle time, so
    total = kernel + user and busy = total - idle.
    Returns 0.0 off Windows or if the call fails.
    """
    if not is_windows():
        return 0.0
    try:
        idle1, kernel1, user1 = _system_times()
        time.sleep(sample_seconds)
        idle2, kernel2, user2 = _system_times()
        idle_delta = idle2 - idle1
        total_delta = (kernel2 - kernel1) + (user2 - user1)
        if total_delta <= 0:
            return 0.0
        busy = total_delta - idle_delta
        return max(0.0, min(100.0, (busy / total_delta) * 100.0))
    except Exception:
        return 0.0


# ----------------------------------------------------------------------
# Chrome window / process helpers
# ----------------------------------------------------------------------
def _chrome_window_handles() -> list:
    """Returns handles of all visible top-level Chrome windows."""
    if not is_windows():
        return []
    user32 = ctypes.windll.user32
    enum_proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    found = []

    def _callback(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, buf, 256)
            if buf.value == "Chrome_WidgetWin_1":
                found.append(hwnd)
        return True

    user32.EnumWindows(enum_proc_type(_callback), 0)
    return found


def count_chrome_windows() -> int:
    return len(_chrome_window_handles())


def _chrome_profile_cmdlines() -> list:
    """Command-line string for every running chrome.exe process, via
    PowerShell's CIM — avoids a psutil dependency. Empty list off
    Windows, if no chrome.exe is running, or if the call fails.
    """
    if not is_windows():
        return []
    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "(Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\").CommandLine",
            ],
            capture_output=True, text=True, timeout=15,
            creationflags=_CREATE_NO_WINDOW,
        )
        return [line for line in result.stdout.splitlines() if line.strip()]
    except Exception:
        return []


def profile_is_open(profile: str, cmdlines: list = None) -> bool:
    """True if a chrome.exe process is currently running with
    --profile-directory=<profile> on its command line. Quote marks are
    stripped before comparing, since Windows quotes a command-line
    argument as a whole (not just the value after "="), so the exact
    quoting around this flag varies depending on how the process was
    launched.

    cmdlines can be passed in (from a single earlier
    _chrome_profile_cmdlines() call) to avoid spawning a fresh
    PowerShell process — which is genuinely slow to start — for every
    profile checked in a batch; see open_profiles(), which checks many
    profiles against one shared snapshot instead of one PowerShell
    launch per profile. Defaults to fetching fresh when called on its
    own.
    """
    if cmdlines is None:
        cmdlines = _chrome_profile_cmdlines()
    target = f"--profile-directory={profile}".lower().replace('"', "")
    return any(target in cmd.lower().replace('"', "") for cmd in cmdlines)


# ----------------------------------------------------------------------
# Opening profiles
# ----------------------------------------------------------------------
def _wait_for_safe_load(cpu_safe: float, ram_safe: float, log) -> None:
    streak = 0
    started = time.time()
    while True:
        cpu, ram = cpu_percent(), ram_percent()
        streak = streak + 1 if (cpu <= cpu_safe and ram <= ram_safe) else 0
        if streak >= SAFE_READINGS_REQUIRED:
            return
        if time.time() - started >= MAX_WAIT_FOR_SAFE_LOAD:
            log("  CPU/RAM স্থিতিশীল হওয়ার অপেক্ষা টাইম-আউট হয়েছে; সাবধানে এগোনো হচ্ছে।")
            return


def _wait_for_new_window(before: int, log) -> bool:
    started = time.time()
    while time.time() - started < MAX_WAIT_FOR_WINDOW:
        time.sleep(1)
        if count_chrome_windows() > before:
            return True
    log("  নতুন উইন্ডো শনাক্ত করতে সময় বেশি লাগছে (তবু চালিয়ে যাওয়া হচ্ছে)।")
    return False


def open_profiles(max_profiles: int = MAX_PROFILES_DEFAULT,
                   cpu_safe: float = CPU_SAFE_DEFAULT,
                   ram_safe: float = RAM_SAFE_DEFAULT,
                   log=None) -> dict:
    """Opens up to max_profiles Chrome profiles, one at a time, waiting
    for CPU/RAM to settle below the safe thresholds before each launch.
    Skips any profile that already has a window open. Calls log(msg)
    with short status updates as it goes.

    Returns {"launched": int, "skipped": int, "failed": int, "total": int}.
    """
    if log is None:
        log = lambda msg: None

    if not is_windows():
        log("Chrome Profile Manager শুধু Windows-এ কাজ করে।")
        return {"launched": 0, "skipped": 0, "failed": 0, "total": 0}

    chrome = find_chrome_exe()
    if chrome is None:
        log("Chrome খুঁজে পাওয়া যায়নি — ইনস্টল করা আছে কিনা দেখুন।")
        return {"launched": 0, "skipped": 0, "failed": 0, "total": 0}

    profiles = list_chrome_profiles()[:max_profiles]
    if not profiles:
        log("কোনো Chrome প্রোফাইল পাওয়া যায়নি।")
        return {"launched": 0, "skipped": 0, "failed": 0, "total": 0}

    log(f"{len(profiles)}টা প্রোফাইল পাওয়া গেছে। একে একে নিরাপদভাবে খোলা হচ্ছে...")

    # Fetched once (one PowerShell process) and reused for every profile
    # below, instead of spawning a fresh PowerShell per profile just to
    # answer the same "what's already open" question — meaningful when
    # opening a large batch, which is the whole point of this feature.
    already_open_cmdlines = _chrome_profile_cmdlines()

    launched = skipped = failed = 0
    for i, profile in enumerate(profiles, 1):
        if profile_is_open(profile, already_open_cmdlines):
            log(f"[{i}/{len(profiles)}] {profile} — ইতিমধ্যে খোলা আছে, স্কিপ করা হলো।")
            skipped += 1
            continue

        _wait_for_safe_load(cpu_safe, ram_safe, log)

        before = count_chrome_windows()
        try:
            subprocess.Popen(
                [str(chrome), f"--profile-directory={profile}", "--new-window"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=_CREATE_NO_WINDOW,
            )
        except Exception as exc:
            log(f"[{i}/{len(profiles)}] {profile} — চালু করা যায়নি: {exc}")
            failed += 1
            continue

        _wait_for_new_window(before, log)
        launched += 1
        log(f"[{i}/{len(profiles)}] {profile} — চালু করা হয়েছে।")

    log(f"শেষ — চালু: {launched}, স্কিপ: {skipped}, ব্যর্থ: {failed}")
    return {"launched": launched, "skipped": skipped, "failed": failed, "total": len(profiles)}


# ----------------------------------------------------------------------
# Closing Chrome + shutdown
# ----------------------------------------------------------------------
def close_all_chrome_windows(log=None, wait_for_exit: bool = True,
                              exit_timeout: float = MAX_WAIT_FOR_CHROME_EXIT) -> bool:
    """Gracefully closes every visible Chrome window (like clicking each
    window's own X button, so Chrome saves/restores session data
    normally). If wait_for_exit, also waits up to exit_timeout seconds
    for chrome.exe to fully exit. Returns True once chrome.exe is
    confirmed closed (or immediately if wait_for_exit is False).
    """
    if log is None:
        log = lambda msg: None
    if not is_windows():
        log("এই ফিচার শুধু Windows-এ কাজ করে।")
        return False

    handles = _chrome_window_handles()
    if not handles:
        log("কোনো Chrome উইন্ডো খোলা পাওয়া যায়নি।")
    else:
        user32 = ctypes.windll.user32
        wm_close = 0x0010
        for hwnd in handles:
            user32.PostMessageW(hwnd, wm_close, 0, 0)
            time.sleep(0.2)
        log(f"{len(handles)}টা Chrome উইন্ডো বন্ধ করার নির্দেশ পাঠানো হয়েছে।")

    if not wait_for_exit:
        return True

    started = time.time()
    while time.time() - started < exit_timeout:
        if not browser_core.is_browser_running("Chrome"):
            log("Chrome পুরোপুরি বন্ধ হয়েছে।")
            return True
        time.sleep(1)
    log("Chrome পুরোপুরি বন্ধ হতে বেশি সময় লাগছে; তাও এগোনো হচ্ছে।")
    return False


def shutdown_pc(log=None) -> bool:
    """Issues an immediate Windows shutdown (`shutdown /s /t 0`)."""
    if log is None:
        log = lambda msg: None
    if not is_windows():
        log("এই ফিচার শুধু Windows-এ কাজ করে।")
        return False
    try:
        subprocess.run(["shutdown", "/s", "/t", "0"])
        log("PC শাটডাউনের নির্দেশ পাঠানো হয়েছে।")
        return True
    except Exception as exc:
        log(f"শাটডাউন করা যায়নি: {exc}")
        return False


def close_chrome_and_shutdown(log=None) -> bool:
    """Closes every Chrome window, waits for chrome.exe to fully exit,
    then shuts the PC down. Returns True only if the shutdown command
    was actually issued.
    """
    close_all_chrome_windows(log=log, wait_for_exit=True)
    return shutdown_pc(log=log)
