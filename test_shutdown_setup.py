"""
Automated tests for shutdown_setup.py.

winreg is a Windows-only stdlib module, so it's replaced with a small
in-memory fake for these tests (same approach as test_startup_manager.py).
subprocess.run (schtasks) and ctypes.windll (IsUserAnAdmin) are mocked
directly since they're plain function calls here, not something with
its own richer fake needed.

Focus of these tests: setup_shutdown_clean() must not report success
in a way that contradicts a Fast-Startup warning it just logged. Real
bug found by inspection: the function used to completely discard
disable_fast_startup()'s return value, so "Fast Startup could not be
disabled" and "Done, this will now run on every shutdown" could both
get logged back to back — the second claim isn't true when the first
one happened, since Windows skips shutdown scripts during Fast Startup.

Run with: python -m unittest test_shutdown_setup.py -v
"""

import unittest
import unittest.mock


class FakeWinReg:
    """Minimal in-memory registry: single values under (hive, path)."""

    HKEY_LOCAL_MACHINE = "HKLM"
    KEY_SET_VALUE = 1
    KEY_READ = 2
    REG_SZ = 1
    REG_DWORD = 4
    REG_BINARY = 3

    def __init__(self):
        self.store = {}
        self.fail_open_on = set()   # {(hive, path)}
        self.fail_set_on = set()    # {(hive, path, name)}
        self.missing_keys = set()   # {(hive, path)} -> OpenKey raises FileNotFoundError

    def _bucket(self, hive, path, create=False):
        key = (hive, path)
        if key not in self.store and create:
            self.store[key] = {}
        return self.store.get(key, {})

    def OpenKey(self, hive, path, *a, **kw):
        key = (hive, path)
        if key in self.fail_open_on:
            raise PermissionError("access denied (fake)")
        if key in self.missing_keys or key not in self.store:
            raise FileNotFoundError("not found (fake)")
        return _FakeKeyHandle(self, hive, path)

    def CreateKeyEx(self, hive, path, *a, **kw):
        key = (hive, path)
        if key in self.fail_open_on:
            raise PermissionError("access denied (fake)")
        self._bucket(hive, path, create=True)
        return _FakeKeyHandle(self, hive, path)

    def SetValueEx(self, key_handle, name, reserved, value_type, value):
        if (key_handle.hive, key_handle.path, name) in self.fail_set_on:
            raise PermissionError("access denied (fake)")
        self._bucket(key_handle.hive, key_handle.path, create=True)[name] = (value, value_type)

    def QueryValueEx(self, key_handle, name):
        bucket = self._bucket(key_handle.hive, key_handle.path)
        if name not in bucket:
            raise FileNotFoundError("value not found (fake)")
        return bucket[name]

    def DeleteKey(self, hive, path):
        key = (hive, path)
        if key not in self.store:
            raise FileNotFoundError("not found (fake)")
        del self.store[key]

    # --- test helpers ---
    def seed_value(self, hive, path, name, value, value_type=4):
        self._bucket(hive, path, create=True)[name] = (value, value_type)

    def get_value(self, hive, path, name):
        return self._bucket(hive, path).get(name)

    def key_exists(self, hive, path):
        return (hive, path) in self.store


class _FakeKeyHandle:
    def __init__(self, fake, hive, path):
        self.fake = fake
        self.hive = hive
        self.path = path

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def Close(self):
        pass


class ShutdownSetupTestCase(unittest.TestCase):
    """Patches shutdown_setup.winreg with a fresh in-memory fake per test
    (create=True since the real import fails on this non-Windows
    sandbox, leaving no such attribute to patch over — same pattern as
    test_startup_manager.py) and forces is_windows() True so the
    Windows-only code paths under test actually run here instead of
    short-circuiting on the platform check.
    """

    @classmethod
    def setUpClass(cls):
        import shutdown_setup
        cls.ss = shutdown_setup

    def setUp(self):
        self.fake = FakeWinReg()
        self._winreg_patch = unittest.mock.patch.object(self.ss, "winreg", self.fake, create=True)
        self._winreg_patch.start()
        self._is_windows_patch = unittest.mock.patch.object(self.ss, "is_windows", return_value=True)
        self._is_windows_patch.start()

    def tearDown(self):
        self._is_windows_patch.stop()
        self._winreg_patch.stop()


class TestFastStartup(ShutdownSetupTestCase):
    def test_disable_writes_zero(self):
        self.fake.seed_value(self.fake.HKEY_LOCAL_MACHINE, self.ss._FAST_STARTUP_KEY, self.ss._FAST_STARTUP_VALUE, 1)
        ok = self.ss.disable_fast_startup(log=lambda m: None)
        self.assertTrue(ok)
        self.assertEqual(
            self.fake.get_value(self.fake.HKEY_LOCAL_MACHINE, self.ss._FAST_STARTUP_KEY, self.ss._FAST_STARTUP_VALUE),
            (0, 4),
        )

    def test_disable_permission_error_returns_false_and_logs(self):
        self.fake.fail_open_on.add((self.fake.HKEY_LOCAL_MACHINE, self.ss._FAST_STARTUP_KEY))
        messages = []
        ok = self.ss.disable_fast_startup(log=messages.append)
        self.assertFalse(ok)
        self.assertTrue(any("admin" in m.lower() for m in messages))

    def test_get_status_true_when_value_is_one(self):
        self.fake.seed_value(self.fake.HKEY_LOCAL_MACHINE, self.ss._FAST_STARTUP_KEY, self.ss._FAST_STARTUP_VALUE, 1)
        self.assertTrue(self.ss.get_fast_startup_status())

    def test_get_status_false_when_value_is_zero(self):
        self.fake.seed_value(self.fake.HKEY_LOCAL_MACHINE, self.ss._FAST_STARTUP_KEY, self.ss._FAST_STARTUP_VALUE, 0)
        self.assertFalse(self.ss.get_fast_startup_status())

    def test_get_status_assumes_disabled_when_key_missing(self):
        # No value seeded at all - key doesn't exist.
        self.assertFalse(self.ss.get_fast_startup_status())


class TestGpoRegistration(ShutdownSetupTestCase):
    def test_register_writes_script_and_parameters(self):
        ok = self.ss._register_gpo(log=lambda m: None)
        self.assertTrue(ok)
        script_val = self.fake.get_value(self.fake.HKEY_LOCAL_MACHINE, self.ss._GPO_SCRIPTS_BASE, "Script")
        self.assertIsNotNone(script_val)
        self.assertTrue(script_val[0], "expected a non-empty interpreter path to be written")
        params_val = self.fake.get_value(self.fake.HKEY_LOCAL_MACHINE, self.ss._GPO_SCRIPTS_BASE, "Parameters")
        self.assertIn("shutdown_clean.py", params_val[0])

    def test_register_permission_error_returns_false(self):
        self.fake.fail_open_on.add((self.fake.HKEY_LOCAL_MACHINE, self.ss._GPO_SCRIPTS_BASE))
        ok = self.ss._register_gpo(log=lambda m: None)
        self.assertFalse(ok)

    def test_is_registered_reflects_key_presence(self):
        self.assertFalse(self.ss._is_gpo_registered())
        self.ss._register_gpo(log=lambda m: None)
        self.assertTrue(self.ss._is_gpo_registered())

    def test_unregister_removes_the_key(self):
        self.ss._register_gpo(log=lambda m: None)
        ok = self.ss._unregister_gpo(log=lambda m: None)
        self.assertTrue(ok)
        self.assertFalse(self.ss._is_gpo_registered())

    def test_unregister_when_already_absent_is_still_success(self):
        ok = self.ss._unregister_gpo(log=lambda m: None)
        self.assertTrue(ok)


class TestTaskSchedulerRegistration(ShutdownSetupTestCase):
    def test_register_calls_schtasks_create(self):
        with unittest.mock.patch.object(
            self.ss.subprocess, "run", return_value=unittest.mock.Mock(returncode=0, stdout="", stderr="")
        ) as mock_run:
            ok = self.ss._register_task(log=lambda m: None)
        self.assertTrue(ok)
        args = mock_run.call_args[0][0]
        self.assertIn("/Create", args)
        self.assertIn(self.ss._TASK_NAME, args)

    def test_register_failure_is_reported(self):
        messages = []
        with unittest.mock.patch.object(
            self.ss.subprocess, "run",
            return_value=unittest.mock.Mock(returncode=1, stdout="", stderr="Access is denied."),
        ):
            ok = self.ss._register_task(log=messages.append)
        self.assertFalse(ok)
        self.assertTrue(any("denied" in m.lower() for m in messages))

    def test_unregister_treats_not_found_as_success(self):
        with unittest.mock.patch.object(
            self.ss.subprocess, "run",
            return_value=unittest.mock.Mock(returncode=1, stdout="", stderr="ERROR: The system cannot find the file specified."),
        ):
            ok = self.ss._unregister_task(log=lambda m: None)
        self.assertTrue(ok)

    def test_is_registered_reflects_query_returncode(self):
        with unittest.mock.patch.object(self.ss.subprocess, "run", return_value=unittest.mock.Mock(returncode=0)):
            self.assertTrue(self.ss._is_task_registered())
        with unittest.mock.patch.object(self.ss.subprocess, "run", return_value=unittest.mock.Mock(returncode=1)):
            self.assertFalse(self.ss._is_task_registered())


class TestSetupShutdownCleanFastStartupWarning(ShutdownSetupTestCase):
    """The actual bug fix: setup_shutdown_clean()'s final message must
    never claim unconditional success when Fast Startup could not be
    disabled - that specific combination silently defeated the whole
    feature (registered, but Windows would never actually run it).
    """

    def setUp(self):
        super().setUp()
        self._admin_patch = unittest.mock.patch.object(self.ss, "_is_admin", return_value=True)
        self._admin_patch.start()
        # The Fast Startup key is a core OS registry path that always
        # exists on a real Windows machine - seed it so disable succeeds
        # by default. Tests that want to simulate the disable actually
        # failing add their own fail_open_on entry, which takes priority.
        self.fake.seed_value(self.fake.HKEY_LOCAL_MACHINE, self.ss._FAST_STARTUP_KEY, self.ss._FAST_STARTUP_VALUE, 1)

    def tearDown(self):
        self._admin_patch.stop()
        super().tearDown()

    def test_both_succeed_no_fast_startup_warning(self):
        messages = []
        ok = self.ss.setup_shutdown_clean(log=messages.append)
        self.assertTrue(ok)
        combined = " ".join(messages).lower()
        self.assertNotIn("fast startup is still on", combined)

    def test_fast_startup_fails_but_gpo_succeeds_still_warns_clearly(self):
        self.fake.fail_open_on.add((self.fake.HKEY_LOCAL_MACHINE, self.ss._FAST_STARTUP_KEY))
        messages = []

        ok = self.ss.setup_shutdown_clean(log=messages.append)

        # The script DID get registered...
        self.assertTrue(ok)
        self.assertTrue(self.ss._is_gpo_registered())
        # ...but the log must clearly say it won't actually run yet,
        # not just an unconditional "done, this will now work".
        combined = " ".join(messages).lower()
        self.assertIn("fast startup is still on", combined)

    def test_fast_startup_and_gpo_both_fail_falls_back_to_task(self):
        self.fake.fail_open_on.add((self.fake.HKEY_LOCAL_MACHINE, self.ss._FAST_STARTUP_KEY))
        self.fake.fail_open_on.add((self.fake.HKEY_LOCAL_MACHINE, self.ss._GPO_SCRIPTS_BASE))
        messages = []

        with unittest.mock.patch.object(
            self.ss.subprocess, "run", return_value=unittest.mock.Mock(returncode=0, stdout="", stderr="")
        ):
            ok = self.ss.setup_shutdown_clean(log=messages.append)

        self.assertTrue(ok)
        combined = " ".join(messages).lower()
        self.assertIn("fast startup is still on", combined)

    def test_everything_fails_returns_false(self):
        self.fake.fail_open_on.add((self.fake.HKEY_LOCAL_MACHINE, self.ss._GPO_SCRIPTS_BASE))
        with unittest.mock.patch.object(
            self.ss.subprocess, "run",
            return_value=unittest.mock.Mock(returncode=1, stdout="", stderr="failed"),
        ):
            ok = self.ss.setup_shutdown_clean(log=lambda m: None)
        self.assertFalse(ok)


class TestGetStatus(ShutdownSetupTestCase):
    def test_reports_nothing_registered_initially(self):
        with unittest.mock.patch.object(self.ss.subprocess, "run", return_value=unittest.mock.Mock(returncode=1)):
            status = self.ss.get_status()
        self.assertFalse(status["gpo_registered"])
        self.assertFalse(status["task_registered"])

    def test_reports_gpo_registered_after_setup(self):
        self.ss._register_gpo(log=lambda m: None)
        with unittest.mock.patch.object(self.ss.subprocess, "run", return_value=unittest.mock.Mock(returncode=1)):
            status = self.ss.get_status()
        self.assertTrue(status["gpo_registered"])


class TestGracefulDegradationOffWindows(unittest.TestCase):
    """Pins the actual bug: shutdown_setup.py used to do a bare
    `import winreg` at module level, which raised ModuleNotFoundError
    immediately on any non-Windows machine — including this Linux CI
    sandbox — so importing pc_cleaner.py (which imports this module)
    crashed before a single test could run. winreg is now optional,
    and every registry-touching function checks is_windows() first.

    Deliberately does NOT use ShutdownSetupTestCase / patch winreg or
    is_windows here — this exercises the real, unpatched behavior on
    the real (non-Windows) sandbox, confirming every entry point
    degrades to a safe default instead of raising.
    """

    def test_module_imported_without_crashing(self):
        # If this test exists and runs at all, the module-level import
        # at the top of this file already succeeded - this assertion
        # just documents *why* that matters.
        import shutdown_setup
        self.assertIsNotNone(shutdown_setup)

    def test_is_windows_false_on_this_sandbox(self):
        import shutdown_setup
        self.assertFalse(shutdown_setup.is_windows())

    def test_registry_functions_return_safe_defaults(self):
        import shutdown_setup as ss
        self.assertFalse(ss.disable_fast_startup(log=lambda m: None))
        self.assertFalse(ss.enable_fast_startup(log=lambda m: None))
        self.assertFalse(ss.get_fast_startup_status())
        self.assertFalse(ss._is_gpo_registered())
        self.assertTrue(ss._unregister_gpo(log=lambda m: None))  # nothing to remove -> success

    def test_register_gpo_reports_unavailable_and_falls_through(self):
        import shutdown_setup as ss
        messages = []
        ok = ss._register_gpo(log=messages.append)
        self.assertFalse(ok)
        self.assertTrue(any("not on windows" in m.lower() for m in messages))


if __name__ == "__main__":
    unittest.main()
