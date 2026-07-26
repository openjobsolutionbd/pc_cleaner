"""
test_integration_gui.py
------------------------
Unlike the other test files, this one actually builds the Tkinter app
(needs a display — works fine on a normal Windows desktop; on Linux CI
it needs Xvfb) and drives its worker methods directly, the same way a
button click would. This is what catches cross-thread bugs that
per-function unit tests can't see (e.g. calling a Tk method from a
background thread).

Run with: python -m unittest test_integration_gui.py -v
"""

import os
import shutil
import tempfile
import time
import unittest
import unittest.mock

import tkinter as tk

import pc_cleaner as wc
import history_log
import scheduler


class TestCleanJunkWorkerIntegration(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as e:
            self.skipTest(f"No display available to run the GUI: {e}")
        self.app = wc.CleanerApp(self.root)

        # Point history logging at a throwaway file for this test
        self.tmp_dir = tempfile.mkdtemp()
        self.log_file = os.path.join(self.tmp_dir, "history.json")
        history_log.default_log_path = lambda: self.log_file

        # Give a fake, safe-to-delete category pointing at a temp folder
        self.fake_target = os.path.join(self.tmp_dir, "fake_temp")
        os.makedirs(self.fake_target)
        with open(os.path.join(self.fake_target, "junk.txt"), "wb") as f:
            f.write(b"x" * 999)

        self.fake_category = {
            "id": "test_fake",
            "name": "Test Fake Category",
            "desc": "test",
            "paths": [self.fake_target],
            "needs_admin": False,
            "default_checked": True,
        }

    def tearDown(self):
        self.app.shutdown()
        self.root.destroy()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _pump(self, ms=800):
        """Runs the real mainloop for a bit so queued UI updates process,
        then stops — mirrors how the shipped app behaves.
        """
        self.root.after(ms, self.root.quit)
        self.root.mainloop()

    def test_clean_worker_deletes_files_and_logs_history(self):
        self.app._clean_junk_worker([self.fake_category])
        self._pump()

        self.assertEqual(os.listdir(self.fake_target), [])

        history = history_log.read_history(self.log_file)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["bytes_freed"], 999)
        self.assertIn("test_fake", history[0]["categories"])

    def test_scan_worker_updates_size_label_without_crashing(self):
        # Don't replace category_size_labels wholesale — the app's own
        # initial scan (kicked off automatically in __init__) may still
        # have queued updates in flight for the real categories.
        self.app.categories = [self.fake_category]
        self.app.category_vars = {"test_fake": tk.BooleanVar(value=True)}
        self.app.category_size_labels["test_fake"] = self.app.total_label  # reuse any real label widget

        self.app._scan_junk_worker()
        self._pump()

        self.assertEqual(self.app.category_sizes["test_fake"], 999)


class TestQuickCleanWorkerIntegration(unittest.TestCase):
    """Quick Clean is meant to be a simpler, always-safe shortcut: it
    must only ever touch categories with badge == "safe", and must
    never silently include a "caution" category even if one is present
    in self.app.categories.
    """

    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as e:
            self.skipTest(f"No display available to run the GUI: {e}")
        self.app = wc.CleanerApp(self.root)

        self.tmp_dir = tempfile.mkdtemp()
        self.log_file = os.path.join(self.tmp_dir, "history.json")
        history_log.default_log_path = lambda: self.log_file

        self.safe_target = os.path.join(self.tmp_dir, "safe_temp")
        self.caution_target = os.path.join(self.tmp_dir, "caution_temp")
        self.admin_target = os.path.join(self.tmp_dir, "admin_temp")
        for d in (self.safe_target, self.caution_target, self.admin_target):
            os.makedirs(d)
        for d in (self.safe_target, self.caution_target, self.admin_target):
            with open(os.path.join(d, "junk.txt"), "wb") as f:
                f.write(b"x" * 500)

        self.app.categories = [
            {
                "id": "fake_safe", "name": "Fake Safe", "desc": "test",
                "paths": [self.safe_target], "needs_admin": False,
                "default_checked": True, "badge": "safe",
            },
            {
                "id": "fake_caution", "name": "Fake Caution", "desc": "test",
                "paths": [self.caution_target], "needs_admin": False,
                "default_checked": False, "badge": "caution",
            },
            {
                "id": "fake_safe_admin", "name": "Fake Safe Admin", "desc": "test",
                "paths": [self.admin_target], "needs_admin": True,
                "default_checked": True, "badge": "safe",
            },
        ]

    def tearDown(self):
        self.app.shutdown()
        self.root.destroy()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _pump(self, ms=800):
        self.root.after(ms, self.root.quit)
        self.root.mainloop()

    def test_only_safe_badge_category_is_cleaned(self):
        with unittest.mock.patch.object(wc.cleaner_core, "is_admin", return_value=True), \
             unittest.mock.patch.object(self.app, "scan_junk"):
            self.app._quick_clean_worker()
            self._pump()

        self.assertEqual(os.listdir(self.safe_target), [], "safe-badge category should be emptied")
        self.assertEqual(
            os.listdir(self.caution_target), ["junk.txt"],
            "caution-badge category must NEVER be touched by Quick Clean",
        )

    def test_needs_admin_safe_category_skipped_when_not_admin(self):
        with unittest.mock.patch.object(wc.cleaner_core, "is_admin", return_value=False), \
             unittest.mock.patch.object(self.app, "scan_junk"):
            self.app._quick_clean_worker()
            self._pump()

        self.assertEqual(os.listdir(self.safe_target), [], "non-admin safe category still cleaned")
        self.assertEqual(
            os.listdir(self.admin_target), ["junk.txt"],
            "admin-required category must be skipped gracefully when not elevated, not crash",
        )

    def test_history_logged_with_quick_mode(self):
        # With is_admin=True, BOTH safe-badge categories qualify (the
        # ordinary one and the admin-required one), so both get cleaned.
        with unittest.mock.patch.object(wc.cleaner_core, "is_admin", return_value=True), \
             unittest.mock.patch.object(self.app, "scan_junk"):
            self.app._quick_clean_worker()
            self._pump()

        history = history_log.read_history(self.log_file)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["mode"], "quick")
        self.assertEqual(history[0]["bytes_freed"], 1000)
        self.assertIn("fake_safe", history[0]["categories"])
        self.assertIn("fake_safe_admin", history[0]["categories"])
        self.assertNotIn("fake_caution", history[0]["categories"])

    def test_history_save_failure_warning_is_not_silently_overwritten(self):
        # Regression test: _quick_clean_done used to set a "couldn't save
        # history" warning on quick_status_label, then immediately
        # overwrite that same label with the plain success message a few
        # lines later — so the warning was set but never actually seen.
        # The freed-space total and the warning must both survive into
        # the one final message shown to the user.
        with unittest.mock.patch.object(wc.cleaner_core, "is_admin", return_value=True), \
             unittest.mock.patch.object(self.app, "scan_junk"), \
             unittest.mock.patch.object(wc.history_log, "log_cleanup", return_value=False):
            self.app._quick_clean_worker()
            self._pump()

        shown_text = self.app.quick_status_label["text"]
        self.assertIn("freed", shown_text, "freed-space total must still be shown")
        self.assertIn("Couldn't save to the history log", shown_text, "save-failure warning must reach the user")
        self.assertEqual(str(self.app.quick_status_label["fg"]), str(wc.Theme.WARNING))

    def test_button_re_enabled_after_run(self):
        self.app.quick_clean_btn.config(state="disabled")
        with unittest.mock.patch.object(wc.cleaner_core, "is_admin", return_value=True), \
             unittest.mock.patch.object(self.app, "scan_junk"):
            self.app._quick_clean_worker()
            self._pump()
        self.assertEqual(str(self.app.quick_clean_btn["state"]), "normal")


class TestAutomationTabIntegration(unittest.TestCase):
    """Bug fix: the "Enable Schedule" button used to run schtasks
    directly on the main thread (freezing the GUI while it ran) and the
    Automation tab had no log box, so the real schtasks error message
    was never shown to the user.
    """

    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as e:
            self.skipTest(f"No display available to run the GUI: {e}")
        self.app = wc.CleanerApp(self.root)

    def tearDown(self):
        self.app.shutdown()
        self.root.destroy()

    def _pump(self, ms=800):
        self.root.after(ms, self.root.quit)
        self.root.mainloop()

    def test_enable_schedule_button_handler_does_not_block(self):
        """The button click handler itself must return almost
        immediately — the slow part (schtasks) has to happen on a
        background thread, not in the button callback."""
        def slow_create(*args, **kwargs):
            time.sleep(0.4)
            return True

        with unittest.mock.patch.object(scheduler, "create_scheduled_task", side_effect=slow_create):
            started = time.monotonic()
            self.app.enable_schedule()  # the real button command
            elapsed = time.monotonic() - started
        self.assertLess(elapsed, 0.2, "enable_schedule() blocked the caller instead of using a background thread")
        self._pump()  # let the background thread finish before teardown

    def test_enable_schedule_failure_shows_the_real_schtasks_message(self):
        """Previously only a generic 'Try Administrator' messagebox was
        shown, regardless of what schtasks actually reported."""
        def fake_create(run_command, frequency, day, time_str, log=None):
            if log:
                log("Could not create schedule: ERROR: Invalid Start Time value.")
            return False

        with unittest.mock.patch.object(scheduler, "create_scheduled_task", side_effect=fake_create):
            self.app.enable_schedule()
            self._pump()

        logged_text = self.app.auto_log.text.get("1.0", "end")
        self.assertIn("Invalid Start Time", logged_text)

    def test_enable_schedule_success_is_logged(self):
        with unittest.mock.patch.object(scheduler, "create_scheduled_task", return_value=True) as mock_create:
            # Reproduce what the real function logs on success, since the
            # mock replaces it entirely.
            def fake_create(run_command, frequency, day, time_str, log=None):
                if log:
                    log(f"Scheduled: runs {frequency.lower()} at {time_str}.")
                return True
            mock_create.side_effect = fake_create

            self.app.enable_schedule()
            self._pump()

        logged_text = self.app.auto_log.text.get("1.0", "end")
        self.assertIn("Scheduled:", logged_text)


class TestScanButtonsDisableDuringWork(unittest.TestCase):
    """Bug fix: Analyze / Scan (Empty Folder Finder) had no "in
    progress" indicator and could be clicked repeatedly to start
    overlapping scans on a large folder.
    """

    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as e:
            self.skipTest(f"No display available to run the GUI: {e}")
        self.app = wc.CleanerApp(self.root)
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        self.app.shutdown()
        self.root.destroy()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _pump(self, ms=800):
        self.root.after(ms, self.root.quit)
        self.root.mainloop()

    def test_analyze_button_disabled_while_scanning_then_re_enabled(self):
        self.app.analyzer_folder = self.tmp_dir
        self.app.run_analyzer()
        self.assertEqual(str(self.app.analyze_btn["state"]), "disabled")
        self._pump()
        self.assertEqual(str(self.app.analyze_btn["state"]), "normal")

    def test_scan_empty_button_disabled_while_scanning_then_re_enabled(self):
        self.app.empty_folder = self.tmp_dir
        self.app.scan_empty_folders()
        self.assertEqual(str(self.app.scan_empty_btn["state"]), "disabled")
        self._pump()
        self.assertEqual(str(self.app.scan_empty_btn["state"]), "normal")


class TestBuildFullCategories(unittest.TestCase):
    """build_full_categories() adds the Recycle Bin on top of the plain
    cleaner_core categories, since it needs the Shell API rather than a
    folder path — make sure it still carries a valid badge like the rest.
    """

    def test_recycle_bin_has_safe_badge_and_is_checked_by_default(self):
        cats = {c["id"]: c for c in wc.build_full_categories()}
        self.assertIn("recycle_bin", cats)
        self.assertEqual(cats["recycle_bin"]["badge"], "safe")
        self.assertTrue(cats["recycle_bin"]["default_checked"])

    def test_all_categories_have_a_badge(self):
        for cat in wc.build_full_categories():
            self.assertIn(cat.get("badge"), ("safe", "caution"))


if __name__ == "__main__":
    unittest.main()
