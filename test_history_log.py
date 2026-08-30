import os
import shutil
import tempfile
import threading
import unittest

import history_log as hl


class TestHistoryLog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.log_file = os.path.join(self.tmp, "sub", "history.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_file_returns_empty_list(self):
        self.assertEqual(hl.read_history(self.log_file), [])

    def test_log_and_read_back(self):
        entry = {"timestamp": "2026-07-20T10:00:00", "categories": ["user_temp"], "bytes_freed": 12345}
        self.assertTrue(hl.log_cleanup(entry, self.log_file))
        history = hl.read_history(self.log_file)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["bytes_freed"], 12345)

    def test_multiple_entries_appended_in_order(self):
        hl.log_cleanup({"run": 1}, self.log_file)
        hl.log_cleanup({"run": 2}, self.log_file)
        hl.log_cleanup({"run": 3}, self.log_file)
        history = hl.read_history(self.log_file)
        self.assertEqual([e["run"] for e in history], [1, 2, 3])

    def test_caps_at_max_entries(self):
        for i in range(hl.MAX_ENTRIES + 10):
            hl.log_cleanup({"run": i}, self.log_file)
        history = hl.read_history(self.log_file)
        self.assertEqual(len(history), hl.MAX_ENTRIES)
        # oldest entries should have been dropped, newest kept
        self.assertEqual(history[-1]["run"], hl.MAX_ENTRIES + 9)

    def test_corrupted_file_treated_as_empty(self):
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        with open(self.log_file, "w") as f:
            f.write("{not valid json")
        self.assertEqual(hl.read_history(self.log_file), [])

    def test_bare_filename_with_no_folder_component_still_works(self):
        """Bug fix: a log_file with no directory part (os.path.dirname
        returns "") used to make os.makedirs("", exist_ok=True) raise,
        which the except OSError caught — so it just silently failed
        instead of writing next to the current directory."""
        cwd = os.getcwd()
        os.chdir(self.tmp)
        try:
            self.assertTrue(hl.log_cleanup({"run": 1}, "bare_history.json"))
            self.assertTrue(os.path.exists(os.path.join(self.tmp, "bare_history.json")))
            history = hl.read_history("bare_history.json")
            self.assertEqual(len(history), 1)
        finally:
            os.chdir(cwd)

    def test_concurrent_writes_do_not_lose_entries(self):
        """Bug fix: log_cleanup() used to read-modify-write the JSON
        file with no locking. This app can call it from more than one
        place around the same moment (Quick Clean tab, Junk Cleanup
        tab, and the separately-launched scheduled auto-clean task), so
        two calls finishing close together could each read the same
        "before" list and then each write their own "after" list —
        whichever wrote second would silently overwrite (lose) the
        other's entry. log_cleanup() now takes an exclusive file lock
        around the read-modify-write so this can't happen.

        Uses a barrier to force the worst-case interleaving (both
        threads about to write at the same instant) rather than relying
        on chance timing, and repeats it many times since a race bug
        can pass on lucky individual runs.
        """
        trials = 30
        entries_lost = 0
        for i in range(trials):
            log_file = os.path.join(self.tmp, f"race_{i}.json")
            barrier = threading.Barrier(2)

            def write(label):
                barrier.wait()
                hl.log_cleanup({"label": label}, log_file)

            t1 = threading.Thread(target=write, args=("A",))
            t2 = threading.Thread(target=write, args=("B",))
            t1.start()
            t2.start()
            t1.join(timeout=5)
            t2.join(timeout=5)

            history = hl.read_history(log_file)
            if len(history) != 2:
                entries_lost += 1

        self.assertEqual(
            entries_lost, 0,
            f"{entries_lost}/{trials} concurrent-write trials lost a history entry",
        )


if __name__ == "__main__":
    unittest.main()
