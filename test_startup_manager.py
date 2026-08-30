"""
Automated tests for startup_manager.py.

winreg is a Windows-only stdlib module — it doesn't exist on this
(Linux) test machine at all, so these tests inject a small in-memory
fake registry in its place. The main thing under test is the
write-then-delete "move a value between two keys" logic in
_move_registry_value, specifically the rollback path used when the
delete-from-source step fails after the copy-to-destination step
already succeeded (the bug: this used to leave the value in both
places, so the item showed up twice — Enabled and Disabled — with a
generic error that didn't explain why).

Run with: python -m unittest test_startup_manager.py -v
"""

import os
import shutil
import tempfile
import unittest
import unittest.mock

import startup_manager as sm


class FakeWinReg:
    """Minimal in-memory stand-in for the winreg module, limited to what
    startup_manager.py actually calls. `fail_delete_on` lets a test force
    DeleteValue to raise for one specific (hive, path, value_name), which
    is how the "copy succeeded, delete failed" scenario is simulated.
    """
    HKEY_CURRENT_USER = "HKCU"
    HKEY_LOCAL_MACHINE = "HKLM"
    KEY_READ = 1
    KEY_ALL_ACCESS = 2

    class _Key:
        def __init__(self, hive, path):
            self.hive = hive
            self.path = path

    def __init__(self):
        self.store = {}          # {(hive, path): {name: (value, type)}}
        self.fail_delete_on = set()   # {(hive, path, name)}
        self.delete_calls = []

    def _bucket(self, hive, path, create=False):
        key = (hive, path)
        if key not in self.store:
            if not create:
                raise FileNotFoundError(f"registry key not found: {path}")
            self.store[key] = {}
        return self.store[key]

    def OpenKey(self, hive, path, res, access):
        self._bucket(hive, path, create=False)  # raises if the key is missing
        return FakeWinReg._Key(hive, path)

    def CreateKeyEx(self, hive, path, res, access):
        self._bucket(hive, path, create=True)
        return FakeWinReg._Key(hive, path)

    def QueryValueEx(self, key, name):
        bucket = self._bucket(key.hive, key.path)
        if name not in bucket:
            raise FileNotFoundError(f"value not found: {name}")
        return bucket[name]

    def SetValueEx(self, key, name, res, value_type, value):
        bucket = self._bucket(key.hive, key.path, create=True)
        bucket[name] = (value, value_type)

    def DeleteValue(self, key, name):
        marker = (key.hive, key.path, name)
        self.delete_calls.append(marker)
        if marker in self.fail_delete_on:
            raise PermissionError("simulated: Access is denied.")
        bucket = self._bucket(key.hive, key.path)
        if name not in bucket:
            raise FileNotFoundError(f"value not found: {name}")
        del bucket[name]

    def CloseKey(self, key):
        pass

    # --- test helpers, not part of the real winreg API ---
    def seed(self, hive, path, name, value=r"C:\app.exe", value_type=1):
        self._bucket(hive, path, create=True)[name] = (value, value_type)

    def has_value(self, hive, path, name):
        return name in self.store.get((hive, path), {})


class StartupManagerTestCase(unittest.TestCase):
    """Patches startup_manager.winreg (created fresh even though the real
    import failed on Linux) and forces is_windows() True for the
    duration of each test."""

    def setUp(self):
        self.fake = FakeWinReg()
        self._winreg_patch = unittest.mock.patch.object(sm, "winreg", self.fake, create=True)
        self._winreg_patch.start()
        self._is_windows_patch = unittest.mock.patch.object(sm, "is_windows", return_value=True)
        self._is_windows_patch.start()

    def tearDown(self):
        self._is_windows_patch.stop()
        self._winreg_patch.stop()


class TestMoveRegistryValueSuccess(StartupManagerTestCase):
    def test_value_ends_up_only_in_destination(self):
        self.fake.seed("HKCU", "from", "MyApp")
        ok = sm._move_registry_value("HKCU", "from", "to", "MyApp", log=lambda m: None)
        self.assertTrue(ok)
        self.assertTrue(self.fake.has_value("HKCU", "to", "MyApp"))
        self.assertFalse(self.fake.has_value("HKCU", "from", "MyApp"))


class TestMoveRegistryValueFailedDeleteRollsBack(StartupManagerTestCase):
    """This is the bug fix: copy succeeds, delete-from-source fails ->
    must not leave the value in both places."""

    def setUp(self):
        super().setUp()
        self.fake.seed("HKCU", "from", "MyApp")
        self.fake.fail_delete_on.add(("HKCU", "from", "MyApp"))
        self.messages = []
        self.result = sm._move_registry_value("HKCU", "from", "to", "MyApp", log=self.messages.append)

    def test_returns_false(self):
        self.assertFalse(self.result)

    def test_no_duplicate_left_in_destination(self):
        self.assertFalse(
            self.fake.has_value("HKCU", "to", "MyApp"),
            "the copy must be rolled back when the delete-from-source fails",
        )

    def test_original_value_is_untouched(self):
        self.assertTrue(self.fake.has_value("HKCU", "from", "MyApp"))
        self.assertEqual(self.fake.store[("HKCU", "from")]["MyApp"], (r"C:\app.exe", 1))

    def test_error_message_explains_what_happened(self):
        combined = " ".join(self.messages)
        self.assertIn("Administrator", combined)
        self.assertIn("duplicat", combined.lower())


class TestMoveRegistryValueRollbackAlsoFails(StartupManagerTestCase):
    """Rare edge case: even the rollback delete (on the destination key)
    fails. The value really is left in both places now — the log message
    must say so plainly rather than staying generic."""

    def setUp(self):
        super().setUp()
        self.fake.seed("HKCU", "from", "MyApp")
        self.fake.fail_delete_on.add(("HKCU", "from", "MyApp"))
        self.fake.fail_delete_on.add(("HKCU", "to", "MyApp"))
        self.messages = []
        self.result = sm._move_registry_value("HKCU", "from", "to", "MyApp", log=self.messages.append)

    def test_returns_false(self):
        self.assertFalse(self.result)

    def test_message_warns_about_a_possible_duplicate(self):
        combined = " ".join(self.messages)
        self.assertIn("twice", combined)


class TestDisableEnableStartupItemUseTheFix(StartupManagerTestCase):
    """End-to-end through the public functions the GUI actually calls,
    not just the private helper — confirms both directions are fixed."""

    def test_disable_registry_item_rolls_back_on_failed_delete(self):
        self.fake.seed("HKCU", sm.RUN_KEY_PATH, "MyApp")
        self.fake.fail_delete_on.add(("HKCU", sm.RUN_KEY_PATH, "MyApp"))
        item = {"id": "registry-hkcu:MyApp", "name": "MyApp", "source": "registry-hkcu", "enabled": True}

        messages = []
        ok = sm.disable_startup_item(item, log=messages.append)

        self.assertFalse(ok)
        self.assertFalse(self.fake.has_value("HKCU", sm.BACKUP_KEY_PATH, "MyApp"))
        self.assertTrue(self.fake.has_value("HKCU", sm.RUN_KEY_PATH, "MyApp"))

    def test_disable_registry_item_succeeds_normally(self):
        self.fake.seed("HKCU", sm.RUN_KEY_PATH, "MyApp")
        item = {"id": "registry-hkcu:MyApp", "name": "MyApp", "source": "registry-hkcu", "enabled": True}
        ok = sm.disable_startup_item(item, log=lambda m: None)
        self.assertTrue(ok)
        self.assertTrue(self.fake.has_value("HKCU", sm.BACKUP_KEY_PATH, "MyApp"))
        self.assertFalse(self.fake.has_value("HKCU", sm.RUN_KEY_PATH, "MyApp"))

    def test_enable_registry_item_rolls_back_on_failed_delete(self):
        self.fake.seed("HKLM", sm.BACKUP_KEY_PATH, "MyApp")
        self.fake.fail_delete_on.add(("HKLM", sm.BACKUP_KEY_PATH, "MyApp"))
        item = {"id": "registry-hklm:MyApp", "name": "MyApp", "source": "registry-hklm", "enabled": False}

        messages = []
        ok = sm.enable_startup_item(item, log=messages.append)

        self.assertFalse(ok)
        self.assertFalse(self.fake.has_value("HKLM", sm.RUN_KEY_PATH, "MyApp"))
        self.assertTrue(self.fake.has_value("HKLM", sm.BACKUP_KEY_PATH, "MyApp"))


class StartupFolderTestCase(unittest.TestCase):
    """The Startup-folder (shortcut file) side of startup_manager.py has
    no winreg involvement at all, but disable/enable_startup_item()
    still gate on is_windows() before reaching it, so that still needs
    patching. APPDATA/PROGRAMDATA point at a throwaway temp directory so
    nothing here ever touches a real Startup folder.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._old_env = {k: os.environ.get(k) for k in ("APPDATA", "PROGRAMDATA")}
        os.environ["APPDATA"] = os.path.join(self.tmp, "AppData", "Roaming")
        os.environ["PROGRAMDATA"] = os.path.join(self.tmp, "ProgramData")
        self._is_windows_patch = unittest.mock.patch.object(sm, "is_windows", return_value=True)
        self._is_windows_patch.start()
        # list_startup_items() always scans the registry too, even when
        # only the folder side is under test here - an empty fake keeps
        # that part a no-op instead of hitting the real (Linux-only-
        # stubbed-out) winreg module.
        self._winreg_patch = unittest.mock.patch.object(sm, "winreg", FakeWinReg(), create=True)
        self._winreg_patch.start()

    def tearDown(self):
        self._winreg_patch.stop()
        self._is_windows_patch.stop()
        for k, v in self._old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _user_startup_folder(self):
        return sm._startup_folders()["user"]

    def _make_shortcut(self, folder, name="MyApp.lnk", content="shortcut"):
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, name)
        with open(path, "w") as f:
            f.write(content)
        return path


class TestMoveFile(StartupFolderTestCase):
    """_move_file() is the folder-item equivalent of
    _move_registry_value() - moves a shortcut file into or out of the
    "Disabled (PCCleaner)" subfolder."""

    def test_moves_the_file_and_returns_true(self):
        folder = self._user_startup_folder()
        src = self._make_shortcut(folder)
        dst_folder = sm._disabled_subfolder(folder)

        ok = sm._move_file(src, dst_folder, log=lambda m: None)

        self.assertTrue(ok)
        self.assertFalse(os.path.exists(src))
        self.assertTrue(os.path.exists(os.path.join(dst_folder, "MyApp.lnk")))

    def test_creates_the_destination_folder_if_missing(self):
        folder = self._user_startup_folder()
        src = self._make_shortcut(folder)
        dst_folder = sm._disabled_subfolder(folder)
        self.assertFalse(os.path.isdir(dst_folder))

        sm._move_file(src, dst_folder, log=lambda m: None)

        self.assertTrue(os.path.isdir(dst_folder))

    def test_content_is_preserved_across_the_move(self):
        folder = self._user_startup_folder()
        src = self._make_shortcut(folder, content="exact bytes must survive")
        dst_folder = sm._disabled_subfolder(folder)

        sm._move_file(src, dst_folder, log=lambda m: None)

        with open(os.path.join(dst_folder, "MyApp.lnk")) as f:
            self.assertEqual(f.read(), "exact bytes must survive")

    def test_missing_source_returns_false_and_logs(self):
        messages = []
        ok = sm._move_file(
            os.path.join(self.tmp, "does_not_exist.lnk"),
            os.path.join(self.tmp, "dest"),
            log=messages.append,
        )
        self.assertFalse(ok)
        self.assertTrue(messages, "expected a log message explaining the failure")

    def test_os_error_during_move_returns_false_not_raises(self):
        folder = self._user_startup_folder()
        src = self._make_shortcut(folder)
        dst_folder = sm._disabled_subfolder(folder)

        with unittest.mock.patch.object(sm.os, "replace", side_effect=OSError("locked")):
            ok = sm._move_file(src, dst_folder, log=lambda m: None)

        self.assertFalse(ok)
        # The source must still be there - a failed move should never
        # leave the file in limbo (neither at the source nor the dest).
        self.assertTrue(os.path.exists(src))


class TestListStartupItemsFolderScan(StartupFolderTestCase):
    def test_finds_an_enabled_shortcut(self):
        folder = self._user_startup_folder()
        self._make_shortcut(folder, "MyApp.lnk")

        items = sm.list_startup_items()

        matches = [i for i in items if i["name"] == "MyApp.lnk"]
        self.assertEqual(len(matches), 1)
        self.assertTrue(matches[0]["enabled"])
        self.assertEqual(matches[0]["source"], "startup-folder-user")

    def test_finds_a_disabled_shortcut_in_the_subfolder(self):
        folder = self._user_startup_folder()
        self._make_shortcut(sm._disabled_subfolder(folder), "MyApp.lnk")

        items = sm.list_startup_items()

        matches = [i for i in items if i["name"] == "MyApp.lnk"]
        self.assertEqual(len(matches), 1)
        self.assertFalse(matches[0]["enabled"])

    def test_the_disabled_subfolder_itself_is_never_listed_as_an_item(self):
        folder = self._user_startup_folder()
        # Just creating the subfolder (e.g. from a past disable), empty.
        os.makedirs(sm._disabled_subfolder(folder))

        items = sm.list_startup_items()

        names = [i["name"] for i in items]
        self.assertNotIn("Disabled (PCCleaner)", names)

    def test_no_startup_folder_at_all_is_not_an_error(self):
        # APPDATA/PROGRAMDATA point at folders that don't exist yet.
        items = sm.list_startup_items()
        self.assertEqual(items, [])


class TestDisableEnableStartupFolderItem(StartupFolderTestCase):
    """End-to-end through the public functions the GUI actually calls."""

    def test_disable_then_enable_round_trip(self):
        folder = self._user_startup_folder()
        self._make_shortcut(folder, "MyApp.lnk")
        item = {
            "id": "folder-user:MyApp.lnk",
            "name": "MyApp.lnk",
            "source": "startup-folder-user",
            "enabled": True,
        }

        self.assertTrue(sm.disable_startup_item(item, log=lambda m: None))
        after_disable = {i["name"]: i["enabled"] for i in sm.list_startup_items()}
        self.assertEqual(after_disable.get("MyApp.lnk"), False)

        disabled_item = {**item, "enabled": False}
        self.assertTrue(sm.enable_startup_item(disabled_item, log=lambda m: None))
        after_enable = {i["name"]: i["enabled"] for i in sm.list_startup_items()}
        self.assertEqual(after_enable.get("MyApp.lnk"), True)

    def test_unknown_scope_returns_false(self):
        item = {"id": "folder-bogus:MyApp.lnk", "name": "MyApp.lnk", "source": "startup-folder-bogus", "enabled": True}
        self.assertFalse(sm.disable_startup_item(item, log=lambda m: None))


if __name__ == "__main__":
    unittest.main()
