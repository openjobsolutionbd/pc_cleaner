import os
import shutil
import tempfile
import threading
import unittest

import error_log as el


class TestErrorLog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.log_file = os.path.join(self.tmp, "sub", "error_log.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_file_returns_empty_list(self):
        self.assertEqual(el.read_errors(self.log_file), [])

    def test_record_and_read_back(self):
        try:
            raise ValueError("boom")
        except ValueError as exc:
            self.assertTrue(el.record("test_context", exc, log_file=self.log_file))
        entries = el.read_errors(self.log_file)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["context"], "test_context")
        self.assertEqual(entries[0]["error_type"], "ValueError")
        self.assertEqual(entries[0]["message"], "boom")
        self.assertIn("traceback", entries[0])
        self.assertIn("timestamp", entries[0])

    def test_record_never_raises_even_when_write_is_impossible(self):
        # A path where a directory should be but a file already sits
        # instead: os.makedirs() will fail. record() must report this
        # as False, not raise — logging a failure must never itself
        # become a new failure the app has to handle.
        blocked = os.path.join(self.tmp, "not_a_dir")
        with open(blocked, "w") as f:
            f.write("x")
        bad_path = os.path.join(blocked, "error_log.json")
        try:
            raise RuntimeError("boom")
        except RuntimeError as exc:
            result = el.record("ctx", exc, log_file=bad_path)
        self.assertFalse(result)

    def test_multiple_entries_appended_in_order(self):
        for i in range(3):
            try:
                raise ValueError(f"err {i}")
            except ValueError as exc:
                el.record(f"ctx{i}", exc, log_file=self.log_file)
        entries = el.read_errors(self.log_file)
        self.assertEqual([e["context"] for e in entries], ["ctx0", "ctx1", "ctx2"])

    def test_caps_at_max_entries(self):
        for i in range(el.MAX_ENTRIES + 10):
            try:
                raise ValueError(f"err {i}")
            except ValueError as exc:
                el.record(f"ctx{i}", exc, log_file=self.log_file)
        entries = el.read_errors(self.log_file)
        self.assertEqual(len(entries), el.MAX_ENTRIES)
        # oldest entries dropped, newest kept
        self.assertEqual(entries[-1]["context"], f"ctx{el.MAX_ENTRIES + 9}")

    def test_corrupted_file_treated_as_empty(self):
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        with open(self.log_file, "w") as f:
            f.write("{not valid json")
        self.assertEqual(el.read_errors(self.log_file), [])

    def test_count_errors(self):
        self.assertEqual(el.count_errors(self.log_file), 0)
        try:
            raise ValueError("x")
        except ValueError as exc:
            el.record("ctx", exc, log_file=self.log_file)
        self.assertEqual(el.count_errors(self.log_file), 1)

    def test_clear_errors_removes_all_entries(self):
        try:
            raise ValueError("x")
        except ValueError as exc:
            el.record("ctx", exc, log_file=self.log_file)
        self.assertEqual(el.count_errors(self.log_file), 1)
        self.assertTrue(el.clear_errors(self.log_file))
        self.assertEqual(el.count_errors(self.log_file), 0)

    def test_clear_errors_when_file_missing_is_still_success(self):
        self.assertTrue(el.clear_errors(self.log_file))

    def test_concurrent_writes_do_not_lose_entries(self):
        """Same guarantee as history_log.py: two errors logged from
        different threads/processes at close to the same instant must
        both survive, not silently overwrite each other. Uses a
        barrier to force the worst-case interleaving rather than
        relying on chance timing, repeated many times since a race bug
        can pass on lucky individual runs.
        """
        trials = 30
        entries_lost = 0
        for i in range(trials):
            log_file = os.path.join(self.tmp, f"race_{i}.json")
            barrier = threading.Barrier(2)

            # barrier/log_file default-bound at definition time (not
            # looked up when the thread later runs) so each iteration's
            # closure can't accidentally see a later iteration's values -
            # moot here since join() happens before the loop advances,
            # but this is the standard, future-proof way to write it.
            def write(label, barrier=barrier, log_file=log_file):
                barrier.wait()
                try:
                    raise ValueError(label)
                except ValueError as exc:
                    el.record(label, exc, log_file=log_file)

            t1 = threading.Thread(target=write, args=("A",))
            t2 = threading.Thread(target=write, args=("B",))
            t1.start()
            t2.start()
            t1.join(timeout=5)
            t2.join(timeout=5)

            entries = el.read_errors(log_file)
            if len(entries) != 2:
                entries_lost += 1

        self.assertEqual(
            entries_lost, 0,
            f"{entries_lost}/{trials} concurrent-write trials lost an error entry",
        )


if __name__ == "__main__":
    unittest.main()
