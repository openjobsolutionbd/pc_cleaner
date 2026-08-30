"""
Automated tests for cleaner_core.py.

These cover the two functions where a bug would be dangerous:
  - get_dir_size   (must not crash, must not touch anything)
  - delete_dir_contents (must delete contents but NEVER the root folder,
                          must skip locked/undeletable files instead of
                          crashing, must report accurate byte counts)

Run with:  python -m unittest test_cleaner_core.py -v
"""

import os
import stat
import shutil
import tempfile
import unittest
import unittest.mock

import cleaner_core as core


class TestFormatSize(unittest.TestCase):
    def test_bytes(self):
        self.assertEqual(core.format_size(500), "500 B")

    def test_kb(self):
        self.assertEqual(core.format_size(2048), "2.0 KB")

    def test_mb(self):
        self.assertEqual(core.format_size(5 * 1024 * 1024), "5.0 MB")

    def test_negative_clamped_to_zero(self):
        self.assertEqual(core.format_size(-100), "0 B")


class TestGetDirSize(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_dir_is_zero(self):
        self.assertEqual(core.get_dir_size(self.tmp), 0)

    def test_nonexistent_path_is_zero(self):
        self.assertEqual(core.get_dir_size(os.path.join(self.tmp, "nope")), 0)

    def test_sums_files_recursively(self):
        with open(os.path.join(self.tmp, "a.txt"), "wb") as f:
            f.write(b"x" * 100)
        sub = os.path.join(self.tmp, "sub")
        os.mkdir(sub)
        with open(os.path.join(sub, "b.txt"), "wb") as f:
            f.write(b"y" * 250)
        self.assertEqual(core.get_dir_size(self.tmp), 350)

    def test_symlinked_file_is_not_counted(self):
        # A symlink shouldn't have its target's size double-counted (or
        # counted at all) - delete_dir_contents never touches symlinks,
        # so the size estimate shouldn't include them either.
        real_file = os.path.join(self.tmp, "real.txt")
        with open(real_file, "wb") as f:
            f.write(b"x" * 500)
        link = os.path.join(self.tmp, "link.txt")
        try:
            os.symlink(real_file, link)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not supported on this platform/OS")
        # Only the real file's 500 bytes should be counted, not the link.
        self.assertEqual(core.get_dir_size(self.tmp), 500)

    def test_symlinked_directory_is_not_followed(self):
        real_dir = os.path.join(self.tmp, "real_dir")
        os.mkdir(real_dir)
        with open(os.path.join(real_dir, "inside.txt"), "wb") as f:
            f.write(b"x" * 999)
        link = os.path.join(self.tmp, "link_dir")
        try:
            os.symlink(real_dir, link, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not supported on this platform/OS")
        # get_dir_size(tmp) walks into real_dir once (999) but must not
        # also walk into link_dir and double-count the same bytes.
        self.assertEqual(core.get_dir_size(self.tmp), 999)

    def test_many_small_files_still_sums_correctly(self):
        # Not a timing benchmark (too environment-dependent to assert a
        # duration in CI) - just confirms the scandir-based rewrite gets
        # the right total on the many-small-files shape that browser
        # cache folders actually have, which is exactly the case the
        # os.walk -> os.scandir switch targets.
        for i in range(500):
            with open(os.path.join(self.tmp, f"f{i}.dat"), "wb") as f:
                f.write(b"x" * 10)
        self.assertEqual(core.get_dir_size(self.tmp), 5000)


class TestDeleteDirContents(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        # In case a test leaves a read-only file behind
        for root, dirs, files in os.walk(self.tmp):
            for name in files + dirs:
                try:
                    os.chmod(os.path.join(root, name), stat.S_IWRITE)
                except OSError:
                    pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_file(self, *parts, content=b"data"):
        path = os.path.join(self.tmp, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(content)
        return path

    def test_root_folder_itself_is_never_deleted(self):
        self._make_file("file.txt")
        core.delete_dir_contents(self.tmp)
        self.assertTrue(os.path.isdir(self.tmp), "root folder must survive cleanup")

    def test_contents_are_removed(self):
        self._make_file("file.txt")
        self._make_file("sub", "nested.txt")
        summary = core.delete_dir_contents(self.tmp)
        self.assertEqual(os.listdir(self.tmp), [])
        self.assertGreater(summary["deleted_bytes"], 0)

    def test_reports_correct_byte_count(self):
        self._make_file("a.txt", content=b"1" * 123)
        self._make_file("b.txt", content=b"2" * 77)
        summary = core.delete_dir_contents(self.tmp)
        self.assertEqual(summary["deleted_bytes"], 200)
        self.assertEqual(summary["deleted_files"], 2)

    def test_nonexistent_path_does_not_raise(self):
        summary = core.delete_dir_contents(os.path.join(self.tmp, "ghost"))
        self.assertEqual(summary["deleted_bytes"], 0)

    def test_locked_file_is_skipped_not_fatal(self):
        # Simulate a file that's in use (permission denied on delete) by
        # mocking os.remove for that one path. Permission *bits* aren't a
        # reliable way to simulate this in tests, since a root/admin
        # process ignores them. Deletion must skip the locked file and
        # keep going rather than raising or aborting the whole cleanup.
        locked_file = self._make_file("cant_touch.txt")
        self._make_file("normal.txt")

        real_remove = os.remove

        def fake_remove(path, *a, **kw):
            if os.path.abspath(path) == os.path.abspath(locked_file):
                raise PermissionError("simulated: file in use")
            return real_remove(path, *a, **kw)

        with unittest.mock.patch("cleaner_core.os.remove", side_effect=fake_remove):
            summary = core.delete_dir_contents(self.tmp)

        # The locked file must still be there (skipped, not force-deleted)
        self.assertTrue(os.path.exists(locked_file))
        self.assertIn(locked_file, summary["skipped"])
        # The normal file should still be gone
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "normal.txt")))
        # Root survives regardless
        self.assertTrue(os.path.isdir(self.tmp))

    def test_file_filter_only_deletes_matching_files(self):
        # Only files whose name starts with "thumb_" should be removed.
        keep = self._make_file("keep_this.dat", content=b"keep")
        delete = self._make_file("thumb_001.db", content=b"gone")
        filt = lambda name: name.startswith("thumb_")
        summary = core.delete_dir_contents(self.tmp, file_filter=filt)
        self.assertFalse(os.path.exists(delete), "matching file must be deleted")
        self.assertTrue(os.path.exists(keep), "non-matching file must survive")
        self.assertEqual(summary["deleted_files"], 1)
        self.assertEqual(summary["deleted_bytes"], 4)

    def test_file_filter_skips_subdirectories(self):
        # When a filter is active, subdirectories are left untouched —
        # the filter is per-filename and directories have no single name
        # to test against.
        sub = os.path.join(self.tmp, "subdir")
        os.mkdir(sub)
        with open(os.path.join(sub, "nested.txt"), "wb") as f:
            f.write(b"data")
        filt = lambda name: name.endswith(".db")
        core.delete_dir_contents(self.tmp, file_filter=filt)
        self.assertTrue(os.path.isdir(sub), "subdirectory must survive when filter is active")

    def test_symlink_file_is_never_deleted(self):
        # Symlink files inside a temp folder must be skipped — deleting
        # the target behind a symlink would break other applications.
        real_file = self._make_file("real.txt", content=b"real")
        link = os.path.join(self.tmp, "link_to_real.txt")
        try:
            os.symlink(real_file, link)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not supported on this platform/OS")
        core.delete_dir_contents(self.tmp)
        # The symlink itself should still be there (we skipped it).
        # The real file can be gone (it wasn't a symlink itself).
        self.assertTrue(os.path.islink(link), "symlink must not be removed")

    def test_windows_only_helpers_are_inert_off_windows(self):
        # On this test machine (Linux), Windows-only helpers must return
        # safe defaults instead of crashing.
        self.assertFalse(core.is_admin())
        self.assertEqual(core.get_recycle_bin_size(), 0)
        self.assertFalse(core.empty_recycle_bin())


class _FakeCompletedProcess:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestWindowsUpdateServiceControl(unittest.TestCase):
    """stop_windows_update_service() now returns a string token instead of
    a bool so callers can distinguish three outcomes:
      "stopped"         — we stopped it (should restart after cleanup)
      "already_stopped" — was already down (safe to proceed, no restart)
      "failed"          — still running (caller must skip this category)
    """

    def test_stop_returns_failed_on_access_denied(self):
        fake_result = _FakeCompletedProcess(2, stderr="System error 5 has occurred. Access is denied.")
        with unittest.mock.patch("cleaner_core.is_windows", return_value=True), \
             unittest.mock.patch("cleaner_core.subprocess.run", return_value=fake_result):
            self.assertEqual(core.stop_windows_update_service(), "failed")

    def test_stop_returns_already_stopped_when_service_not_running(self):
        # "net stop" exits nonzero but prints "has not been started" when
        # the service is already down — this is safe, not a real failure.
        fake_result = _FakeCompletedProcess(2, stderr="The service has not been started.")
        with unittest.mock.patch("cleaner_core.is_windows", return_value=True), \
             unittest.mock.patch("cleaner_core.subprocess.run", return_value=fake_result):
            self.assertEqual(core.stop_windows_update_service(), "already_stopped")

    def test_stop_logs_reason_on_real_failure(self):
        fake_result = _FakeCompletedProcess(2, stderr="Access is denied.")
        messages = []
        with unittest.mock.patch("cleaner_core.is_windows", return_value=True), \
             unittest.mock.patch("cleaner_core.subprocess.run", return_value=fake_result):
            core.stop_windows_update_service(log=messages.append)
        self.assertTrue(any("Access is denied" in m for m in messages))

    def test_stop_does_not_log_when_already_stopped(self):
        # "already stopped" is not an error — nothing should be logged.
        fake_result = _FakeCompletedProcess(2, stderr="The service has not been started.")
        messages = []
        with unittest.mock.patch("cleaner_core.is_windows", return_value=True), \
             unittest.mock.patch("cleaner_core.subprocess.run", return_value=fake_result):
            core.stop_windows_update_service(log=messages.append)
        self.assertEqual(messages, [])

    def test_stop_returns_stopped_on_success(self):
        fake_result = _FakeCompletedProcess(0)
        with unittest.mock.patch("cleaner_core.is_windows", return_value=True), \
             unittest.mock.patch("cleaner_core.subprocess.run", return_value=fake_result):
            self.assertEqual(core.stop_windows_update_service(), "stopped")

    def test_start_returns_false_on_nonzero_returncode(self):
        fake_result = _FakeCompletedProcess(2, stderr="The service has not been started.")
        with unittest.mock.patch("cleaner_core.is_windows", return_value=True), \
             unittest.mock.patch("cleaner_core.subprocess.run", return_value=fake_result):
            self.assertFalse(core.start_windows_update_service())

    def test_start_returns_true_on_success(self):
        fake_result = _FakeCompletedProcess(0)
        with unittest.mock.patch("cleaner_core.is_windows", return_value=True), \
             unittest.mock.patch("cleaner_core.subprocess.run", return_value=fake_result):
            self.assertTrue(core.start_windows_update_service())


class TestBuildCategories(unittest.TestCase):
    def test_returns_list_with_required_keys(self):
        cats = core.build_categories()
        self.assertGreater(len(cats), 0)
        for cat in cats:
            for key in ("id", "name", "desc", "paths", "needs_admin", "default_checked", "badge"):
                self.assertIn(key, cat)

    def test_ids_are_unique(self):
        cats = core.build_categories()
        ids = [c["id"] for c in cats]
        self.assertEqual(len(ids), len(set(ids)))

    def test_badge_is_either_safe_or_caution(self):
        cats = core.build_categories()
        for cat in cats:
            self.assertIn(cat["badge"], ("safe", "caution"))

    def test_caution_categories_default_off(self):
        # Anything marked "caution" must start unchecked — the user opts
        # in, rather than it being cleaned automatically by default.
        cats = {c["id"]: c for c in core.build_categories()}
        for cat_id in ("crash_dumps", "prefetch"):
            self.assertEqual(cats[cat_id]["badge"], "caution")
            self.assertFalse(cats[cat_id]["default_checked"])

    def test_daily_safe_categories_default_on(self):
        # The everyday-safe categories must stay checked by default so a
        # routine clean covers them without extra taps.
        cats = {c["id"]: c for c in core.build_categories()}
        for cat_id in (
            "user_temp", "windows_temp", "chrome_cache", "edge_cache",
            "thumbnail_cache", "wer_reports",
        ):
            self.assertEqual(cats[cat_id]["badge"], "safe")
            self.assertTrue(cats[cat_id]["default_checked"])

    def test_windows_update_categories_are_not_present(self):
        # These were removed once Windows Update was permanently disabled
        # at the OS level (see disable_windows_update.reg/.bat) — keeping
        # them meant every run tried to stop an already-Disabled service
        # and logged a confusing failure message for no benefit.
        ids = {c["id"] for c in core.build_categories()}
        self.assertNotIn("windows_update_cache", ids)
        self.assertNotIn("delivery_optimization", ids)


class TestChromiumCachePaths(unittest.TestCase):
    """Chrome/Edge cache cleaning covers every profile (not just Default)
    and every known cache-type subfolder (not just the main HTTP cache) —
    these are the folders that quietly bloat and slow a browser down over
    time. This still shows up in the UI as a single "Chrome Browser
    Cache" checkbox; only what's behind it got more thorough.
    """

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

    def _make_profile(self, browser_root, profile_name):
        profile_dir = os.path.join(self.localapp, *browser_root, "User Data", profile_name)
        os.makedirs(profile_dir, exist_ok=True)
        with open(os.path.join(profile_dir, "Preferences"), "w") as f:
            f.write("{}")
        return profile_dir

    def test_covers_every_chrome_profile_not_just_default(self):
        self._make_profile(("Google", "Chrome"), "Default")
        self._make_profile(("Google", "Chrome"), "Profile 1")

        cats = {c["id"]: c for c in core.build_categories()}
        paths = cats["chrome_cache"]["paths"]

        self.assertTrue(any(os.path.join("Default", "Cache") in p for p in paths))
        self.assertTrue(any(os.path.join("Profile 1", "Cache") in p for p in paths))

    def test_covers_more_than_just_the_main_cache_folder(self):
        self._make_profile(("Google", "Chrome"), "Default")

        cats = {c["id"]: c for c in core.build_categories()}
        paths = cats["chrome_cache"]["paths"]

        for subfolder in ("Code Cache", "GPUCache"):
            self.assertTrue(
                any(subfolder in p for p in paths),
                f"expected a path containing {subfolder!r}, got {paths}",
            )
        self.assertTrue(any(os.path.join("Service Worker", "CacheStorage") in p for p in paths))

    def test_edge_and_chrome_paths_never_mix(self):
        self._make_profile(("Google", "Chrome"), "Default")
        self._make_profile(("Microsoft", "Edge"), "Default")

        cats = {c["id"]: c for c in core.build_categories()}
        chrome_paths = cats["chrome_cache"]["paths"]
        edge_paths = cats["edge_cache"]["paths"]

        self.assertTrue(all("Chrome" in p for p in chrome_paths))
        self.assertTrue(all("Edge" in p for p in edge_paths))

    def test_no_profiles_means_empty_paths_not_a_crash(self):
        cats = {c["id"]: c for c in core.build_categories()}
        self.assertEqual(cats["chrome_cache"]["paths"], [])
        self.assertEqual(cats["edge_cache"]["paths"], [])

    def test_profile_folders_are_scanned_only_once_for_both_browsers(self):
        # Performance regression guard: building the chrome_cache and
        # edge_cache categories together used to call
        # browser_core.get_browser_profiles() twice (once per browser),
        # even though that single call already scans both browsers'
        # profile folders. build_categories() now fetches it once and
        # shares the result between both categories.
        self._make_profile(("Google", "Chrome"), "Default")
        self._make_profile(("Microsoft", "Edge"), "Default")

        real_fn = core.browser_core.get_browser_profiles
        call_count = 0

        def counting_wrapper():
            nonlocal call_count
            call_count += 1
            return real_fn()

        with unittest.mock.patch.object(
            core.browser_core, "get_browser_profiles", side_effect=counting_wrapper
        ):
            core.build_categories()

        self.assertEqual(call_count, 1)


class TestIsAdmin(unittest.TestCase):
    def test_off_windows_returns_false(self):
        with unittest.mock.patch.object(core, "is_windows", return_value=False):
            self.assertFalse(core.is_admin())

    def test_reflects_the_windows_api_result(self):
        fake_windll = unittest.mock.MagicMock()
        fake_windll.shell32.IsUserAnAdmin.return_value = 1
        with unittest.mock.patch.object(core, "is_windows", return_value=True), \
             unittest.mock.patch("cleaner_core.ctypes.windll", fake_windll, create=True):
            self.assertTrue(core.is_admin())

    def test_a_raised_error_is_caught_not_propagated(self):
        fake_windll = unittest.mock.MagicMock()
        fake_windll.shell32.IsUserAnAdmin.side_effect = OSError("boom")
        with unittest.mock.patch.object(core, "is_windows", return_value=True), \
             unittest.mock.patch("cleaner_core.ctypes.windll", fake_windll, create=True):
            self.assertFalse(core.is_admin())


class TestGetRecycleBinSize(unittest.TestCase):
    def test_off_windows_returns_zero(self):
        with unittest.mock.patch.object(core, "is_windows", return_value=False):
            self.assertEqual(core.get_recycle_bin_size(), 0)

    def test_nonzero_hresult_means_the_size_is_not_trusted(self):
        # If the query call itself fails, don't report whatever happens to
        # be sitting in the (possibly stale/uninitialized) info struct.
        fake_windll = unittest.mock.MagicMock()
        fake_windll.shell32.SHQueryRecycleBinW.return_value = 1  # any non-zero HRESULT
        with unittest.mock.patch.object(core, "is_windows", return_value=True), \
             unittest.mock.patch("cleaner_core.ctypes.windll", fake_windll, create=True):
            self.assertEqual(core.get_recycle_bin_size(), 0)

    def test_a_raised_error_is_caught_not_propagated(self):
        fake_windll = unittest.mock.MagicMock()
        fake_windll.shell32.SHQueryRecycleBinW.side_effect = OSError("boom")
        with unittest.mock.patch.object(core, "is_windows", return_value=True), \
             unittest.mock.patch("cleaner_core.ctypes.windll", fake_windll, create=True):
            self.assertEqual(core.get_recycle_bin_size(), 0)


class TestEmptyRecycleBin(unittest.TestCase):
    """empty_recycle_bin() must not trust SHEmptyRecycleBinW's HRESULT on
    its own — that specific API is documented (and confirmed by real-world
    bug reports against PowerShell's own Clear-RecycleBin cmdlet) to
    return a non-zero/error code even when the Recycle Bin was already
    empty. The only reliable signal is the actual state afterward, which
    is what these tests check.
    """

    def test_off_windows_returns_false(self):
        with unittest.mock.patch.object(core, "is_windows", return_value=False):
            self.assertFalse(core.empty_recycle_bin())

    def test_reports_success_when_bin_ends_up_empty(self):
        with unittest.mock.patch.object(core, "is_windows", return_value=True), \
             unittest.mock.patch("cleaner_core.ctypes.windll", create=True), \
             unittest.mock.patch.object(core, "get_recycle_bin_size", return_value=0):
            self.assertTrue(core.empty_recycle_bin())

    def test_reports_failure_when_bin_still_has_content_afterward(self):
        with unittest.mock.patch.object(core, "is_windows", return_value=True), \
             unittest.mock.patch("cleaner_core.ctypes.windll", create=True), \
             unittest.mock.patch.object(core, "get_recycle_bin_size", return_value=1024):
            self.assertFalse(core.empty_recycle_bin())

    def test_already_empty_quirky_hresult_is_still_reported_as_success(self):
        # Regression guard for the exact bug this fix addresses: a
        # non-zero HRESULT (e.g. E_UNEXPECTED) from an "already empty"
        # bin must NOT be treated as a failure.
        fake_windll = unittest.mock.MagicMock()
        fake_windll.shell32.SHEmptyRecycleBinW.return_value = -2147418113  # E_UNEXPECTED
        with unittest.mock.patch.object(core, "is_windows", return_value=True), \
             unittest.mock.patch("cleaner_core.ctypes.windll", fake_windll, create=True), \
             unittest.mock.patch.object(core, "get_recycle_bin_size", return_value=0):
            self.assertTrue(core.empty_recycle_bin())

    def test_a_raised_error_is_caught_not_propagated(self):
        fake_windll = unittest.mock.MagicMock()
        fake_windll.shell32.SHEmptyRecycleBinW.side_effect = OSError("boom")
        with unittest.mock.patch.object(core, "is_windows", return_value=True), \
             unittest.mock.patch("cleaner_core.ctypes.windll", fake_windll, create=True):
            self.assertFalse(core.empty_recycle_bin())


if __name__ == "__main__":
    unittest.main()
