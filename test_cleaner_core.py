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
    """Bug fix: `net stop`/`net start` returning a nonzero exit code (the
    command ran, but failed) must be reported as failure. Previously the
    function returned True as long as subprocess.run() didn't raise,
    regardless of what net.exe actually reported.
    """

    def test_stop_returns_false_on_nonzero_returncode(self):
        fake_result = _FakeCompletedProcess(2, stderr="System error 5 has occurred. Access is denied.")
        with unittest.mock.patch("cleaner_core.is_windows", return_value=True), \
             unittest.mock.patch("cleaner_core.subprocess.run", return_value=fake_result):
            self.assertFalse(core.stop_windows_update_service())

    def test_stop_logs_the_real_reason_on_failure(self):
        fake_result = _FakeCompletedProcess(2, stderr="Access is denied.")
        messages = []
        with unittest.mock.patch("cleaner_core.is_windows", return_value=True), \
             unittest.mock.patch("cleaner_core.subprocess.run", return_value=fake_result):
            core.stop_windows_update_service(log=messages.append)
        self.assertTrue(any("Access is denied" in m for m in messages))

    def test_stop_returns_true_on_success(self):
        fake_result = _FakeCompletedProcess(0)
        with unittest.mock.patch("cleaner_core.is_windows", return_value=True), \
             unittest.mock.patch("cleaner_core.subprocess.run", return_value=fake_result):
            self.assertTrue(core.stop_windows_update_service())

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
        for cat_id in ("windows_update_cache", "crash_dumps", "prefetch"):
            self.assertEqual(cats[cat_id]["badge"], "caution")
            self.assertFalse(cats[cat_id]["default_checked"])

    def test_daily_safe_categories_default_on(self):
        # The everyday-safe categories must stay checked by default so a
        # routine clean covers them without extra taps.
        cats = {c["id"]: c for c in core.build_categories()}
        for cat_id in (
            "user_temp", "windows_temp", "chrome_cache", "edge_cache",
            "thumbnail_cache", "wer_reports", "delivery_optimization",
        ):
            self.assertEqual(cats[cat_id]["badge"], "safe")
            self.assertTrue(cats[cat_id]["default_checked"])


if __name__ == "__main__":
    unittest.main()
