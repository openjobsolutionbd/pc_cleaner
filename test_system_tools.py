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


if __name__ == "__main__":
    unittest.main()
