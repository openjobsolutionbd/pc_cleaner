import os
import sqlite3
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

import browser_core as bc


def _make_fake_history_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT, title TEXT)")
    conn.execute("CREATE TABLE visits (id INTEGER PRIMARY KEY, url INTEGER, visit_time INTEGER)")
    conn.execute("INSERT INTO urls (url, title) VALUES ('https://example.com', 'Example')")
    conn.execute("INSERT INTO visits (url, visit_time) VALUES (1, 123456)")
    conn.commit()
    conn.close()


def _make_fake_cookies_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE cookies (host_key TEXT, name TEXT, value TEXT)")
    conn.execute("INSERT INTO cookies VALUES ('example.com', 'session', 'super-secret-login-token')")
    conn.commit()
    conn.close()


class TestClearBrowsingHistory(unittest.TestCase):
    def setUp(self):
        self.profile_dir = tempfile.mkdtemp()
        self.history_path = os.path.join(self.profile_dir, "History")
        self.cookies_path = os.path.join(self.profile_dir, "Cookies")
        _make_fake_history_db(self.history_path)
        _make_fake_cookies_db(self.cookies_path)

    def tearDown(self):
        shutil.rmtree(self.profile_dir, ignore_errors=True)

    def test_history_rows_are_deleted(self):
        self.assertEqual(bc.get_history_entry_count(self.profile_dir), 1)
        result = bc.clear_browsing_history(self.profile_dir)
        self.assertTrue(result)
        self.assertEqual(bc.get_history_entry_count(self.profile_dir), 0)

    def test_cookies_file_is_never_modified(self):
        """The core safety guarantee: clearing history must not touch
        Cookies at all — not the file's bytes, not its contents."""
        with open(self.cookies_path, "rb") as f:
            before = f.read()
        bc.clear_browsing_history(self.profile_dir)
        with open(self.cookies_path, "rb") as f:
            after = f.read()
        self.assertEqual(before, after, "Cookies file changed — this must never happen")

        conn = sqlite3.connect(self.cookies_path)
        rows = conn.execute("SELECT value FROM cookies").fetchall()
        conn.close()
        self.assertEqual(rows, [("super-secret-login-token",)])

    def test_missing_history_file_is_not_an_error(self):
        os.remove(self.history_path)
        result = bc.clear_browsing_history(self.profile_dir)
        self.assertTrue(result)

    def test_get_history_entry_count_missing_file_returns_zero(self):
        os.remove(self.history_path)
        self.assertEqual(bc.get_history_entry_count(self.profile_dir), 0)

    def test_stale_wal_file_does_not_resurrect_cleared_history(self):
        """Real bug found by inspection: if the History file was left in
        WAL mode with an uncheckpointed -wal file next to it - completely
        normal after an abnormal shutdown (crash, force-kill, power
        loss) - clear_browsing_history() used to leave that ORIGINAL
        -wal file behind untouched after writing back the cleared copy.
        The next time anything opened the profile, SQLite would replay
        the stale WAL's old frames on top of the freshly-cleared file -
        bringing the "deleted" row right back.

        Reproduced with a genuinely orphaned WAL file (a subprocess
        that commits a WAL write then exits via os._exit(), skipping
        all cleanup - so by the time clear_browsing_history() runs,
        there is no live connection anywhere, exactly like a crashed
        Chrome, only the leftover -wal file on disk).
        """
        script = (
            "import sqlite3\n"
            f"conn = sqlite3.connect({self.history_path!r})\n"
            "conn.execute('PRAGMA journal_mode=WAL')\n"
            "conn.execute(\"INSERT INTO urls (url, title) VALUES ('https://second-site.example', 'x')\")\n"
            "conn.commit()\n"
            "import os\n"
            "os._exit(0)\n"
        )
        subprocess.run([sys.executable, "-c", script], check=True)
        self.assertTrue(
            os.path.exists(self.history_path + "-wal"),
            "test setup failed to produce an orphaned -wal file",
        )

        result = bc.clear_browsing_history(self.profile_dir)
        self.assertTrue(result)
        self.assertFalse(
            os.path.exists(self.history_path + "-wal"),
            "a stale -wal file was left behind next to the cleared History file",
        )

        # The real-world check: does a completely fresh connection (this
        # is what Chrome itself would do on next launch) see the data as
        # cleared, or does the stale WAL bring it back?
        fresh = sqlite3.connect(self.history_path)
        rows = fresh.execute("SELECT url FROM urls").fetchall()
        fresh.close()
        self.assertEqual(rows, [], "cleared history reappeared after reopening - the stale WAL resurrected it")


class TestClearedHistoryIsNotRecoverableFromTheFile(unittest.TestCase):
    """Regression: clearing history used to empty the tables but leave the
    old URLs/titles readable in the file's free pages whenever SQLite's
    secure_delete is off (its stock default, e.g. in Python on Windows).
    Every test here forces secure_delete OFF for the connection the app
    opens, so the result doesn't depend on which platform runs the test.
    """

    MARKER = b"secret-site-7.example.com"

    def setUp(self):
        self.profile_dir = tempfile.mkdtemp()
        self.history_path = os.path.join(self.profile_dir, "History")
        conn = sqlite3.connect(self.history_path)
        conn.execute("CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT, title TEXT)")
        conn.execute("CREATE TABLE visits (id INTEGER PRIMARY KEY, url INTEGER, visit_time INTEGER)")
        conn.execute("CREATE TABLE keep_me (id INTEGER PRIMARY KEY, note TEXT)")
        for i in range(200):
            conn.execute(
                "INSERT INTO urls (url, title) VALUES (?, ?)",
                (f"https://secret-site-{i}.example.com/private/page", f"Private title {i}"),
            )
            conn.execute("INSERT INTO visits (url, visit_time) VALUES (?, ?)", (i + 1, i))
        conn.execute("INSERT INTO keep_me (note) VALUES ('untouched')")
        conn.commit()
        conn.close()

    def tearDown(self):
        shutil.rmtree(self.profile_dir, ignore_errors=True)

    def _clear_with_secure_delete_off(self, vacuum_fails=False):
        real_connect = sqlite3.connect

        class _Conn:
            def __init__(self, conn):
                self._conn = conn

            def execute(self, sql, *args):
                if vacuum_fails and sql.strip().upper() == "VACUUM":
                    raise sqlite3.OperationalError("disk full (simulated)")
                return self._conn.execute(sql, *args)

            def __getattr__(self, name):
                return getattr(self._conn, name)

        def connect_off(*args, **kwargs):
            conn = real_connect(*args, **kwargs)
            conn.execute("PRAGMA secure_delete=OFF")
            return _Conn(conn)

        with unittest.mock.patch.object(bc.sqlite3, "connect", connect_off):
            return bc.clear_browsing_history(self.profile_dir)

    def _file_bytes(self):
        with open(self.history_path, "rb") as f:
            return f.read()

    def test_marker_is_present_before_clearing(self):
        # Guards the other tests: they only mean something if the data is
        # really in the file to begin with.
        self.assertIn(self.MARKER, self._file_bytes())

    def test_deleted_urls_are_gone_from_the_file_bytes(self):
        self.assertTrue(self._clear_with_secure_delete_off())
        self.assertEqual(bc.get_history_entry_count(self.profile_dir), 0)
        data = self._file_bytes()
        self.assertNotIn(self.MARKER, data)
        self.assertNotIn(b"Private title 7", data)

    def test_other_tables_survive(self):
        self.assertTrue(self._clear_with_secure_delete_off())
        conn = sqlite3.connect(self.history_path)
        try:
            rows = conn.execute("SELECT note FROM keep_me").fetchall()
        finally:
            conn.close()
        self.assertEqual(rows, [("untouched",)])

    def test_failed_vacuum_does_not_fail_the_clear_and_still_wipes(self):
        # If VACUUM can't run (e.g. disk full) the clear must still
        # succeed, and secure_delete alone must already have zeroed the
        # deleted rows.
        self.assertTrue(self._clear_with_secure_delete_off(vacuum_fails=True))
        self.assertEqual(bc.get_history_entry_count(self.profile_dir), 0)
        self.assertNotIn(self.MARKER, self._file_bytes())


def _make_profile(user_data_dir, profile_name):
    """Creates a fake Chrome/Edge profile folder with the "Preferences"
    marker file real profiles always have."""
    profile_dir = os.path.join(user_data_dir, profile_name)
    os.makedirs(profile_dir, exist_ok=True)
    with open(os.path.join(profile_dir, "Preferences"), "w") as f:
        f.write("{}")
    return profile_dir


class TestBrowserProfileDetection(unittest.TestCase):
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

    def test_no_profiles_when_no_localappdata(self):
        old = os.environ.pop("LOCALAPPDATA", None)
        try:
            self.assertEqual(bc._browser_profiles(), {})
        finally:
            if old is not None:
                os.environ["LOCALAPPDATA"] = old

    def test_finds_only_default_when_thats_all_that_exists(self):
        chrome_dir = os.path.join(self.localapp, "Google", "Chrome", "User Data")
        _make_profile(chrome_dir, "Default")
        profiles = bc._browser_profiles()
        self.assertEqual(list(profiles.keys()), ["Chrome (Default)"])

    def test_finds_multiple_chrome_profiles_not_just_default(self):
        """The reported bug: only "Default" was ever scanned, so a second
        (or third) Chrome profile's cache/history was silently skipped."""
        chrome_dir = os.path.join(self.localapp, "Google", "Chrome", "User Data")
        _make_profile(chrome_dir, "Default")
        _make_profile(chrome_dir, "Profile 1")
        _make_profile(chrome_dir, "Profile 2")
        profiles = bc._browser_profiles()
        self.assertEqual(
            list(profiles.keys()),
            ["Chrome (Default)", "Chrome (Profile 1)", "Chrome (Profile 2)"],
        )

    def test_finds_profiles_across_both_browsers(self):
        chrome_dir = os.path.join(self.localapp, "Google", "Chrome", "User Data")
        edge_dir = os.path.join(self.localapp, "Microsoft", "Edge", "User Data")
        _make_profile(chrome_dir, "Default")
        _make_profile(edge_dir, "Default")
        _make_profile(edge_dir, "Profile 1")
        profiles = bc._browser_profiles()
        self.assertEqual(
            set(profiles.keys()),
            {"Chrome (Default)", "Edge (Default)", "Edge (Profile 1)"},
        )

    def test_value_carries_the_plain_browser_name_and_correct_path(self):
        """Callers need the plain browser name (not the per-profile label)
        to check whether that browser's process is running."""
        chrome_dir = os.path.join(self.localapp, "Google", "Chrome", "User Data")
        profile_dir = _make_profile(chrome_dir, "Profile 1")
        profiles = bc._browser_profiles()
        browser_name, path = profiles["Chrome (Profile 1)"]
        self.assertEqual(browser_name, "Chrome")
        self.assertEqual(path, profile_dir)

    def test_non_profile_folders_under_user_data_are_ignored(self):
        """Folders like Crashpad/ShaderCache sit alongside real profiles
        under "User Data" but aren't profiles (no Preferences file)."""
        chrome_dir = os.path.join(self.localapp, "Google", "Chrome", "User Data")
        _make_profile(chrome_dir, "Default")
        os.makedirs(os.path.join(chrome_dir, "Crashpad"), exist_ok=True)  # no Preferences file
        os.makedirs(os.path.join(chrome_dir, "ShaderCache"), exist_ok=True)
        profiles = bc._browser_profiles()
        self.assertEqual(list(profiles.keys()), ["Chrome (Default)"])


if __name__ == "__main__":
    unittest.main()
