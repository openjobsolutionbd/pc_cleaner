"""Tests for settings.py (the tiny local settings file)."""

import json
import os
import shutil
import tempfile
import unittest

import i18n
import settings


class TestSettings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "sub", "settings.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_file_means_defaults(self):
        self.assertEqual(settings.load_settings(self.path), {})
        self.assertEqual(settings.get_language(self.path), i18n.DEFAULT_LANG)

    def test_save_and_load_round_trip_including_bangla_text(self):
        self.assertTrue(settings.save_settings({"language": "bn", "note": "বাংলা"}, self.path))
        self.assertEqual(settings.load_settings(self.path), {"language": "bn", "note": "বাংলা"})

    def test_set_and_get_language(self):
        self.assertTrue(settings.set_language("en", self.path))
        self.assertEqual(settings.get_language(self.path), "en")
        self.assertTrue(settings.set_language("bn", self.path))
        self.assertEqual(settings.get_language(self.path), "bn")

    def test_unknown_language_is_rejected_and_nothing_is_written(self):
        self.assertFalse(settings.set_language("fr", self.path))
        self.assertFalse(os.path.exists(self.path))

    def test_saved_junk_language_falls_back_to_the_default(self):
        settings.save_settings({"language": "klingon"}, self.path)
        self.assertEqual(settings.get_language(self.path), i18n.DEFAULT_LANG)

    def test_other_settings_survive_a_language_change(self):
        settings.save_settings({"keep": 1}, self.path)
        settings.set_language("en", self.path)
        self.assertEqual(settings.load_settings(self.path), {"keep": 1, "language": "en"})

    def test_corrupt_file_is_treated_as_empty(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "w") as f:
            f.write("{not valid json")
        self.assertEqual(settings.load_settings(self.path), {})
        self.assertEqual(settings.get_language(self.path), i18n.DEFAULT_LANG)

    def test_a_file_holding_a_list_is_treated_as_empty(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "w") as f:
            json.dump([1, 2, 3], f)
        self.assertEqual(settings.load_settings(self.path), {})

    def test_failed_save_returns_false_instead_of_raising(self):
        blocked = os.path.join(self.tmp, "not_a_dir")
        with open(blocked, "w") as f:
            f.write("x")
        self.assertFalse(settings.save_settings({"a": 1}, os.path.join(blocked, "settings.json")))

    def test_no_temp_file_is_left_behind(self):
        settings.save_settings({"a": 1}, self.path)
        self.assertEqual(os.listdir(os.path.dirname(self.path)), ["settings.json"])


if __name__ == "__main__":
    unittest.main()
