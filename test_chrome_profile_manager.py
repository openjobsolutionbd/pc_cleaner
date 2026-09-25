import os
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import chrome_profile_manager as cpm


def _make_profile(user_data_dir, profile_name):
    """Creates a fake Chrome profile folder with the "Preferences" marker
    file real profiles always have (same helper shape as
    test_browser_core.py, so both modules are tested the same way)."""
    profile_dir = os.path.join(user_data_dir, profile_name)
    os.makedirs(profile_dir, exist_ok=True)
    with open(os.path.join(profile_dir, "Preferences"), "w") as f:
        f.write("{}")
    return profile_dir


class TestListChromeProfiles(unittest.TestCase):
    def setUp(self):
        self.localapp = tempfile.mkdtemp()
        self._old_localapp = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = self.localapp

    def tearDown(self):
        if self._old_localapp is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._old_localapp
        shutil.rmtree(self.localapp, ignore_errors=True)

    def test_no_profiles_when_none_exist(self):
        self.assertEqual(cpm.list_chrome_profiles(), [])

    def test_lists_chrome_profiles_in_stable_order(self):
        chrome_dir = os.path.join(self.localapp, "Google", "Chrome", "User Data")
        _make_profile(chrome_dir, "Default")
        _make_profile(chrome_dir, "Profile 2")
        _make_profile(chrome_dir, "Profile 1")
        self.assertEqual(
            cpm.list_chrome_profiles(), ["Default", "Profile 1", "Profile 2"]
        )

    def test_edge_profiles_are_never_included(self):
        """This module only ever opens Chrome — an Edge-only profile
        must not show up here, even though browser_core tracks both."""
        chrome_dir = os.path.join(self.localapp, "Google", "Chrome", "User Data")
        edge_dir = os.path.join(self.localapp, "Microsoft", "Edge", "User Data")
        _make_profile(chrome_dir, "Default")
        _make_profile(edge_dir, "Default")
        _make_profile(edge_dir, "Profile 1")
        self.assertEqual(cpm.list_chrome_profiles(), ["Default"])


class TestProfileIsOpen(unittest.TestCase):
    def test_matches_profile_directory_flag_case_insensitively(self):
        with patch.object(
            cpm, "_chrome_profile_cmdlines",
            return_value=[r'"C:\chrome.exe" --Profile-Directory="Profile 1" --new-window'],
        ):
            self.assertTrue(cpm.profile_is_open("Profile 1"))
            self.assertFalse(cpm.profile_is_open("Profile 2"))

    def test_no_running_chrome_means_no_profile_is_open(self):
        with patch.object(cpm, "_chrome_profile_cmdlines", return_value=[]):
            self.assertFalse(cpm.profile_is_open("Default"))


class TestFindChromeExe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._old_env = {
            k: os.environ.get(k)
            for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")
        }

    def tearDown(self):
        for k, v in self._old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_returns_none_when_chrome_is_nowhere(self):
        os.environ["PROGRAMFILES"] = self.tmp
        os.environ["PROGRAMFILES(X86)"] = self.tmp
        os.environ["LOCALAPPDATA"] = self.tmp
        self.assertIsNone(cpm.find_chrome_exe())

    def test_finds_chrome_under_localappdata_per_user_install(self):
        os.environ["PROGRAMFILES"] = self.tmp
        os.environ["PROGRAMFILES(X86)"] = self.tmp
        os.environ["LOCALAPPDATA"] = self.tmp
        chrome_path = os.path.join(self.tmp, "Google", "Chrome", "Application", "chrome.exe")
        os.makedirs(os.path.dirname(chrome_path), exist_ok=True)
        open(chrome_path, "w").close()
        self.assertEqual(str(cpm.find_chrome_exe()), chrome_path)


class TestWindowsOnlyGuards(unittest.TestCase):
    """This test suite runs on Linux CI, so the real Windows API calls
    are never reachable — what we CAN verify cross-platform is that
    every public entry point recognizes non-Windows and returns a safe,
    harmless default instead of raising."""

    def test_ram_percent_is_zero_off_windows(self):
        with patch.object(cpm, "is_windows", return_value=False):
            self.assertEqual(cpm.ram_percent(), 0.0)

    def test_cpu_percent_is_zero_off_windows(self):
        with patch.object(cpm, "is_windows", return_value=False):
            self.assertEqual(cpm.cpu_percent(sample_seconds=0), 0.0)

    def test_count_chrome_windows_is_zero_off_windows(self):
        with patch.object(cpm, "is_windows", return_value=False):
            self.assertEqual(cpm.count_chrome_windows(), 0)

    def test_open_profiles_is_a_no_op_off_windows(self):
        with patch.object(cpm, "is_windows", return_value=False):
            result = cpm.open_profiles(log=lambda m: None)
        self.assertEqual(result, {"launched": 0, "skipped": 0, "failed": 0, "total": 0})

    def test_close_chrome_and_shutdown_is_a_no_op_off_windows(self):
        with patch.object(cpm, "is_windows", return_value=False):
            result = cpm.close_chrome_and_shutdown(log=lambda m: None)
        self.assertFalse(result)


class TestRamAndCpuFailureHandling(unittest.TestCase):
    """GlobalMemoryStatusEx and GetSystemTimes both return a BOOL success
    flag that used to be silently ignored — a failed call would leave the
    output struct holding stale/zeroed memory, which was then reported
    as if it were a real (usually 0%) reading instead of "unknown". These
    tests confirm a failure is now recognized and turned into the
    documented 0.0 fallback instead of trusting unwritten memory.
    """

    def test_ram_percent_returns_zero_when_the_api_call_reports_failure(self):
        fake_windll = MagicMock()
        fake_windll.kernel32.GlobalMemoryStatusEx.return_value = 0  # BOOL False
        with patch.object(cpm, "is_windows", return_value=True), \
             patch("chrome_profile_manager.ctypes.windll", fake_windll, create=True):
            self.assertEqual(cpm.ram_percent(), 0.0)

    def test_cpu_percent_returns_zero_when_the_api_call_reports_failure(self):
        fake_windll = MagicMock()
        fake_windll.kernel32.GetSystemTimes.return_value = 0  # BOOL False
        with patch.object(cpm, "is_windows", return_value=True), \
             patch("chrome_profile_manager.ctypes.windll", fake_windll, create=True):
            self.assertEqual(cpm.cpu_percent(sample_seconds=0), 0.0)


class TestOpenProfilesLogic(unittest.TestCase):
    """Exercises the orchestration logic (skip / launch / count) with the
    Windows-only pieces mocked out, so the actual decision-making is
    covered without needing a real Chrome or a real Windows box."""

    def _run(self, profiles, already_open=frozenset(), popen_side_effect=None):
        messages = []
        with patch.object(cpm, "is_windows", return_value=True), \
             patch.object(cpm, "find_chrome_exe", return_value="C:\\fake\\chrome.exe"), \
             patch.object(cpm, "list_chrome_profiles", return_value=profiles), \
             patch.object(cpm, "_chrome_profile_cmdlines", return_value=[]), \
             patch.object(cpm, "profile_is_open", side_effect=lambda p, c=None: p in already_open), \
             patch.object(cpm, "_wait_for_safe_load", return_value=None), \
             patch.object(cpm, "_wait_for_new_window", return_value=True), \
             patch.object(cpm, "count_chrome_windows", return_value=0), \
             patch("chrome_profile_manager.subprocess.Popen", side_effect=popen_side_effect) as mock_popen:
            result = cpm.open_profiles(log=messages.append)
        return result, messages, mock_popen

    def test_already_open_profiles_are_skipped_not_relaunched(self):
        result, messages, mock_popen = self._run(
            ["Default", "Profile 1"], already_open={"Default"}
        )
        self.assertEqual(result, {"launched": 1, "skipped": 1, "failed": 0, "total": 2})
        mock_popen.assert_called_once()
        self.assertTrue(any("Default" in m and "স্কিপ" in m for m in messages))

    def test_launch_failure_is_counted_and_does_not_stop_the_rest(self):
        result, _messages, _mock_popen = self._run(
            ["Default", "Profile 1"], popen_side_effect=[OSError("boom"), None]
        )
        self.assertEqual(result, {"launched": 1, "skipped": 0, "failed": 1, "total": 2})

    def test_no_profiles_found_returns_all_zero_and_does_not_launch_chrome(self):
        result, _messages, mock_popen = self._run([])
        self.assertEqual(result, {"launched": 0, "skipped": 0, "failed": 0, "total": 0})
        mock_popen.assert_not_called()

    def test_respects_max_profiles_limit(self):
        messages = []
        with patch.object(cpm, "is_windows", return_value=True), \
             patch.object(cpm, "find_chrome_exe", return_value="C:\\fake\\chrome.exe"), \
             patch.object(cpm, "list_chrome_profiles", return_value=["Default", "Profile 1", "Profile 2"]), \
             patch.object(cpm, "_chrome_profile_cmdlines", return_value=[]), \
             patch.object(cpm, "profile_is_open", return_value=False), \
             patch.object(cpm, "_wait_for_safe_load", return_value=None), \
             patch.object(cpm, "_wait_for_new_window", return_value=True), \
             patch.object(cpm, "count_chrome_windows", return_value=0), \
             patch("chrome_profile_manager.subprocess.Popen") as mock_popen:
            result = cpm.open_profiles(max_profiles=2, log=messages.append)
        self.assertEqual(result["total"], 2)
        self.assertEqual(mock_popen.call_count, 2)

    def test_already_open_check_spawns_powershell_only_once_per_batch(self):
        # Performance regression guard: profile_is_open() spawns a real
        # PowerShell process (slow to start) to answer "what's currently
        # running". open_profiles() used to call it once PER PROFILE in
        # the loop - for a big batch (this feature's whole reason to
        # exist) that's many redundant PowerShell cold-starts to answer
        # the same question. It must now be fetched once and shared.
        with patch.object(cpm, "is_windows", return_value=True), \
             patch.object(cpm, "find_chrome_exe", return_value="C:\\fake\\chrome.exe"), \
             patch.object(cpm, "list_chrome_profiles", return_value=["Default", "Profile 1", "Profile 2"]), \
             patch.object(cpm, "_chrome_profile_cmdlines", return_value=[]) as mock_cmdlines, \
             patch.object(cpm, "_wait_for_safe_load", return_value=None), \
             patch.object(cpm, "_wait_for_new_window", return_value=True), \
             patch.object(cpm, "count_chrome_windows", return_value=0), \
             patch("chrome_profile_manager.subprocess.Popen"):
            cpm.open_profiles(log=lambda m: None)
        self.assertEqual(mock_cmdlines.call_count, 1)


class TestPidsForExe(unittest.TestCase):
    """_pids_for_exe() is what makes the Chrome/Edge distinction
    possible at all — everything below assumes it correctly separates
    "this window's class name looks like Chrome" from "this window is
    actually owned by a chrome.exe process"."""

    def test_off_windows_returns_empty_set(self):
        with patch.object(cpm, "is_windows", return_value=False):
            self.assertEqual(cpm._pids_for_exe("chrome.exe"), set())

    def test_parses_pids_from_tasklist_csv_output(self):
        # Real `tasklist /FO CSV /NH` output shape: one quoted-CSV line
        # per running process, PID is the second field.
        csv_output = (
            '"chrome.exe","1234","Console","1","123,456 K"\r\n'
            '"chrome.exe","5678","Console","1","98,765 K"\r\n'
        )
        with patch.object(cpm, "is_windows", return_value=True), \
             patch("chrome_profile_manager.subprocess.run",
                   return_value=MagicMock(stdout=csv_output, returncode=0)):
            self.assertEqual(cpm._pids_for_exe("chrome.exe"), {1234, 5678})

    def test_no_matching_process_returns_empty_set(self):
        # tasklist prints this exact message (localized) when the filter
        # matches nothing - not a CSV data line, must not be parsed as one.
        with patch.object(cpm, "is_windows", return_value=True), \
             patch("chrome_profile_manager.subprocess.run",
                   return_value=MagicMock(stdout="INFO: No tasks match the specified criteria.", returncode=0)):
            self.assertEqual(cpm._pids_for_exe("chrome.exe"), set())

    def test_subprocess_failure_returns_empty_set_not_raises(self):
        with patch.object(cpm, "is_windows", return_value=True), \
             patch("chrome_profile_manager.subprocess.run", side_effect=OSError("boom")):
            self.assertEqual(cpm._pids_for_exe("chrome.exe"), set())


class TestFilterChromeHandles(unittest.TestCase):
    """The actual regression guard for the reported bug: Microsoft Edge
    is Chromium-based and shares Chrome's exact window class name
    ("Chrome_WidgetWin_1"), so a window matching that class is NOT
    necessarily Chrome. A window only counts if its owning process id
    is in the chrome.exe pid set."""

    def test_chrome_owned_window_is_kept(self):
        candidates = [(111, 100)]
        self.assertEqual(cpm._filter_chrome_handles(candidates, {100}), [111])

    def test_edge_window_with_matching_class_but_different_pid_is_excluded(self):
        # hwnd 111 -> real Chrome (pid 100); hwnd 222 -> Edge sharing the
        # same window class, but owned by a different (non-Chrome) pid.
        candidates = [(111, 100), (222, 200)]
        self.assertEqual(cpm._filter_chrome_handles(candidates, {100}), [111])

    def test_no_chrome_pids_excludes_everything(self):
        candidates = [(111, 100), (222, 200)]
        self.assertEqual(cpm._filter_chrome_handles(candidates, set()), [])

    def test_multiple_chrome_windows_all_kept(self):
        candidates = [(111, 100), (222, 100), (333, 300)]
        self.assertEqual(cpm._filter_chrome_handles(candidates, {100, 300}), [111, 222, 333])


class TestChromeWindowHandlesEndToEnd(unittest.TestCase):
    """Wires _pids_for_exe + the EnumWindows callback together with a
    fake user32, confirming the process-id cross-check actually happens
    inside _chrome_window_handles() itself, not just in the pure
    helper above."""

    def _fake_user32(self, windows):
        """windows: list of (hwnd, class_name, pid)."""
        user32 = MagicMock()

        def enum_windows(callback, lparam):
            for hwnd, _cls, _pid in windows:
                callback(hwnd, lparam)
            return True

        def get_class_name_w(hwnd, buf, _size):
            cls = next(c for h, c, _p in windows if h == hwnd)
            buf.value = cls
            return len(cls)

        def get_window_thread_process_id(hwnd, pid_ptr):
            pid = next(p for h, _c, p in windows if h == hwnd)
            pid_ptr.contents.value = pid
            return 1

        user32.EnumWindows.side_effect = enum_windows
        user32.IsWindowVisible.return_value = True
        user32.GetClassNameW.side_effect = get_class_name_w
        user32.GetWindowThreadProcessId.side_effect = get_window_thread_process_id
        return user32

    def test_edge_window_never_included_even_with_identical_class_name(self):
        windows = [
            (1, "Chrome_WidgetWin_1", 100),  # real Chrome window
            (2, "Chrome_WidgetWin_1", 200),  # Edge window, same class
        ]
        fake_windll = MagicMock(user32=self._fake_user32(windows))
        # WINFUNCTYPE doesn't exist on this non-Windows sandbox at all
        # (unlike CFUNCTYPE); stand in with an identity wrapper so the
        # real callback closure in _chrome_window_handles() still runs
        # unmodified against our fake user32.EnumWindows above.
        with patch.object(cpm, "is_windows", return_value=True), \
             patch.object(cpm, "_pids_for_exe", return_value={100}), \
             patch("chrome_profile_manager.ctypes.windll", fake_windll, create=True), \
             patch("chrome_profile_manager.ctypes.WINFUNCTYPE", lambda *a, **k: (lambda f: f), create=True):
            handles = cpm._chrome_window_handles()
        self.assertEqual(handles, [1])

    def test_no_chrome_process_running_skips_enumeration_entirely(self):
        with patch.object(cpm, "is_windows", return_value=True), \
             patch.object(cpm, "_pids_for_exe", return_value=set()):
            self.assertEqual(cpm._chrome_window_handles(), [])


class TestCloseAllChromeWindows(unittest.TestCase):
    def test_no_open_windows_is_reported_and_not_an_error(self):
        messages = []
        with patch.object(cpm, "is_windows", return_value=True), \
             patch.object(cpm, "_chrome_window_handles", return_value=[]), \
             patch.object(cpm.browser_core, "is_browser_running", return_value=False):
            result = cpm.close_all_chrome_windows(log=messages.append)
        self.assertTrue(result)
        self.assertTrue(any("কোনো Chrome উইন্ডো" in m for m in messages))

    def test_returns_false_if_chrome_never_fully_exits(self):
        with patch.object(cpm, "is_windows", return_value=True), \
             patch.object(cpm, "_chrome_window_handles", return_value=[]), \
             patch.object(cpm.browser_core, "is_browser_running", return_value=True), \
             patch.object(cpm.time, "sleep", return_value=None):
            result = cpm.close_all_chrome_windows(log=lambda m: None, exit_timeout=0)
        self.assertFalse(result)


class TestShutdownPc(unittest.TestCase):
    def test_issues_shutdown_command(self):
        with patch.object(cpm, "is_windows", return_value=True), \
             patch("chrome_profile_manager.subprocess.run") as mock_run:
            result = cpm.shutdown_pc(log=lambda m: None)
        self.assertTrue(result)
        mock_run.assert_called_once_with(["shutdown", "/s", "/t", "0"])

    def test_shutdown_command_failure_is_reported_not_raised(self):
        messages = []
        with patch.object(cpm, "is_windows", return_value=True), \
             patch("chrome_profile_manager.subprocess.run", side_effect=OSError("no permission")):
            result = cpm.shutdown_pc(log=messages.append)
        self.assertFalse(result)
        self.assertTrue(any("করা যায়নি" in m for m in messages))


if __name__ == "__main__":
    unittest.main()
