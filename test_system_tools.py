import os
import shutil
import tempfile
import unittest

import system_tools as st


class TestFindEmptyFolders(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_empty_folders(self):
        os.makedirs(os.path.join(self.tmp, "a"))
        with open(os.path.join(self.tmp, "a", "file.txt"), "w") as f:
            f.write("x")
        self.assertEqual(st.find_empty_folders(self.tmp), [])

    def test_finds_directly_empty_folder(self):
        empty = os.path.join(self.tmp, "empty1")
        os.makedirs(empty)
        result = st.find_empty_folders(self.tmp)
        self.assertEqual(result, [empty])

    def test_root_itself_never_included(self):
        # root has nothing in it at all -> still must not report root
        result = st.find_empty_folders(self.tmp)
        self.assertEqual(result, [])

    def test_finds_nested_empty_chain_deepest_first(self):
        nested = os.path.join(self.tmp, "a", "b", "c")
        os.makedirs(nested)
        result = st.find_empty_folders(self.tmp)
        # all three levels are "effectively empty"; deepest listed first
        expected_order = [nested, os.path.dirname(nested), os.path.dirname(os.path.dirname(nested))]
        self.assertEqual(result, expected_order)

    def test_folder_with_only_files_in_subfolder_not_flagged(self):
        sub = os.path.join(self.tmp, "hasfile", "sub")
        os.makedirs(sub)
        with open(os.path.join(sub, "keep.txt"), "w") as f:
            f.write("data")
        result = st.find_empty_folders(self.tmp)
        self.assertEqual(result, [])


class TestDeleteEmptyFolders(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_deletes_listed_folders(self):
        empty = os.path.join(self.tmp, "empty1")
        os.makedirs(empty)
        summary = st.delete_empty_folders([empty])
        self.assertEqual(summary["deleted"], 1)
        self.assertFalse(os.path.exists(empty))

    def test_skips_nonexistent_without_raising(self):
        ghost = os.path.join(self.tmp, "ghost")
        summary = st.delete_empty_folders([ghost])
        self.assertEqual(summary["deleted"], 0)
        self.assertIn(ghost, summary["skipped"])

    def test_skips_folder_that_gained_a_file(self):
        folder = os.path.join(self.tmp, "surprise")
        os.makedirs(folder)
        with open(os.path.join(folder, "new.txt"), "w") as f:
            f.write("oops")
        summary = st.delete_empty_folders([folder])
        self.assertEqual(summary["deleted"], 0)
        self.assertTrue(os.path.exists(folder))


class TestAnalyzeFolder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_root_returns_empty_list(self):
        self.assertEqual(st.analyze_folder(self.tmp), [])

    def test_sorted_by_size_descending(self):
        with open(os.path.join(self.tmp, "small.txt"), "wb") as f:
            f.write(b"x" * 10)
        with open(os.path.join(self.tmp, "big.txt"), "wb") as f:
            f.write(b"x" * 1000)
        result = st.analyze_folder(self.tmp)
        self.assertEqual([r["name"] for r in result], ["big.txt", "small.txt"])

    def test_includes_directories_with_recursive_size(self):
        sub = os.path.join(self.tmp, "folder")
        os.makedirs(sub)
        with open(os.path.join(sub, "a.txt"), "wb") as f:
            f.write(b"x" * 500)
        result = st.analyze_folder(self.tmp)
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["is_dir"])
        self.assertEqual(result[0]["size"], 500)

    def test_nonexistent_root_returns_empty_list(self):
        self.assertEqual(st.analyze_folder(os.path.join(self.tmp, "nope")), [])


class TestProtectedRootGuard(unittest.TestCase):
    """Covers the root/critical-folder protection added to system_tools:
    is_drive_root, is_protected_root, and their enforcement inside
    find_empty_folders / delete_empty_folders / analyze_folder.
    """

    def test_is_drive_root_windows_style(self):
        self.assertTrue(st.is_drive_root("C:\\"))
        self.assertTrue(st.is_drive_root("C:/"))
        self.assertTrue(st.is_drive_root("D:\\"))

    def test_is_drive_root_posix_style(self):
        self.assertTrue(st.is_drive_root("/"))

    def test_is_drive_root_false_for_normal_folder(self):
        self.assertFalse(st.is_drive_root("C:\\Users\\Me\\Downloads"))
        self.assertFalse(st.is_drive_root("/home/me/Downloads"))

    def test_protected_folder_names_blocked(self):
        self.assertTrue(st.is_protected_root("C:\\Windows"))
        self.assertTrue(st.is_protected_root("C:\\Program Files"))
        self.assertTrue(st.is_protected_root("C:\\Users"))
        self.assertTrue(st.is_protected_root("C:\\Windows\\System32"))

    def test_documents_blocked_only_directly_under_users(self):
        self.assertTrue(st.is_protected_root("C:\\Users\\Me\\Documents"))
        self.assertTrue(st.is_protected_root("C:\\Users\\Me\\Desktop"))
        # A folder that merely SHARES the name "Documents" somewhere
        # unrelated to a user profile is not what this guard is for.
        self.assertFalse(st.is_protected_root("D:\\Projects\\Documents"))

    def test_subfolder_of_protected_folder_is_not_protected(self):
        # Only the critical folder itself is blocked; legitimate cleanup
        # *inside* Documents/Downloads must still work.
        self.assertFalse(st.is_protected_root("C:\\Users\\Me\\Documents\\OldReports"))
        self.assertFalse(st.is_protected_root("C:\\Users\\Me\\Downloads\\Installers"))

    def test_ordinary_folder_not_protected(self):
        self.assertFalse(st.is_protected_root("C:\\Games\\SomeApp\\cache"))

    def test_empty_path_is_protected(self):
        self.assertTrue(st.is_protected_root(""))
        self.assertTrue(st.is_protected_root(None))

    def test_find_empty_folders_refuses_drive_root(self):
        # "/" is this sandbox's drive-root equivalent; must return []
        # instead of walking the whole filesystem.
        self.assertEqual(st.find_empty_folders("/"), [])

    def test_find_empty_folders_refuses_named_protected_folder(self):
        tmp = tempfile.mkdtemp()
        try:
            fake_users_documents = os.path.join(tmp, "Users", "Me", "Documents")
            os.makedirs(fake_users_documents)
            # Even though it's technically empty, scanning a folder whose
            # own name is a protected one must be refused outright.
            self.assertEqual(st.find_empty_folders(fake_users_documents), [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_find_empty_folders_still_works_for_subfolder_of_protected(self):
        tmp = tempfile.mkdtemp()
        try:
            docs = os.path.join(tmp, "Users", "Me", "Documents")
            old_reports = os.path.join(docs, "OldReports")
            empty_inside = os.path.join(old_reports, "2019")
            os.makedirs(empty_inside)
            # Documents itself is protected (refuses to be scanned as a
            # root), but a subfolder *inside* Documents is an ordinary
            # folder and scanning within it must still work normally.
            result = st.find_empty_folders(old_reports)
            self.assertEqual(result, [empty_inside])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_delete_empty_folders_refuses_protected_path_even_if_passed_directly(self):
        # Simulates a protected path reaching delete_empty_folders by some
        # other route than find_empty_folders — the second, independent
        # check at deletion time must still catch it.
        summary = st.delete_empty_folders(["/"])
        self.assertEqual(summary["deleted"], 0)
        self.assertIn("/", summary["skipped"])
        self.assertTrue(os.path.isdir("/"))  # still exists, obviously

    def test_analyze_folder_refuses_drive_root(self):
        self.assertEqual(st.analyze_folder("/"), [])


class TestDriveHelpers(unittest.TestCase):
    def test_list_drives_returns_at_least_one_drive(self):
        drives = st.list_drives()
        self.assertGreaterEqual(len(drives), 1)
        for d in drives:
            self.assertIn("path", d)
            self.assertIn("total", d)
            self.assertIn("used", d)
            self.assertIn("free", d)
            self.assertGreater(d["total"], 0)

    def test_get_free_space_valid_path(self):
        result = st.get_free_space(os.getcwd())
        self.assertIsNotNone(result)
        total, used, free = result
        self.assertGreater(total, 0)
        self.assertGreaterEqual(free, 0)

    def test_get_free_space_invalid_path_returns_none(self):
        result = st.get_free_space("/this/path/should/not/exist/at/all/12345")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
