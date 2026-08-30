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
