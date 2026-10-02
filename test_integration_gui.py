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
import unittest
import unittest.mock

import tkinter as tk

import pc_cleaner as wc
import history_log


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


class TestTabStructure(unittest.TestCase):
    """The app has exactly four tabs: Quick Clean, Junk Cleanup,
    Browser && Network, Startup Manager. Chrome Profile Manager and
    Shutdown Auto-Clean were removed in v1.5.0 at the user's request;
    the Startup Manager was kept.
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

    def test_exactly_four_tabs(self):
        notebook = self.app.tab_quick.master
        self.assertEqual(len(notebook.tabs()), 4)

    def test_startup_manager_tab_is_present_and_named(self):
        notebook = self.app.tab_quick.master
        titles = [notebook.tab(t, "text") for t in notebook.tabs()]
        self.assertIn("Startup Manager", titles)
        self.assertTrue(hasattr(self.app, "startup_tree"))

    def test_removed_tabs_are_not_attributes(self):
        for name in ("tab_tools", "tab_auto"):
            self.assertFalse(hasattr(self.app, name), name)

    def test_removed_widgets_are_gone(self):
        for name in ("shutdown_status_label", "shutdown_log",
                     "open_chrome_profiles_btn", "close_chrome_shutdown_btn"):
            self.assertFalse(hasattr(self.app, name), name)


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
