"""
Tests for i18n.py: every piece of text exists in BOTH languages with the
same {placeholders}, lookups fall back safely, and every key the GUI asks
for really exists (so a typo can never show a raw key on screen).
"""

import os
import re
import unittest
import unittest.mock

import i18n

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


class TestCatalog(unittest.TestCase):
    def test_every_key_has_both_languages_non_empty(self):
        for key, entry in i18n.STRINGS.items():
            with self.subTest(key=key):
                for lang in i18n.LANGS:
                    self.assertTrue(entry.get(lang, "").strip(), f"{key} missing {lang}")

    def test_both_languages_use_the_same_placeholders(self):
        for key, entry in i18n.STRINGS.items():
            with self.subTest(key=key):
                self.assertEqual(
                    sorted(_PLACEHOLDER.findall(entry["en"])),
                    sorted(_PLACEHOLDER.findall(entry["bn"])),
                )

    def test_no_entry_has_an_unknown_language(self):
        for key, entry in i18n.STRINGS.items():
            with self.subTest(key=key):
                self.assertTrue(set(entry) <= set(i18n.LANGS))

    def test_bangla_text_really_contains_bangla_letters_where_expected(self):
        # Guards against a copy-paste leaving English in the Bangla column
        # for ordinary sentences (brand/technical-only strings are exempt).
        exempt = {"cat.recycle_bin.name", "br.log.result", "st.log.result", "app.tagline_dummy"}
        bangla = re.compile("[\u0980-\u09FF]")
        for key, entry in i18n.STRINGS.items():
            if key in exempt:
                continue
            with self.subTest(key=key):
                self.assertTrue(bangla.search(entry["bn"]) or key == "lang.switch", key)


class TestLookup(unittest.TestCase):
    def setUp(self):
        self._saved = i18n.get_language()

    def tearDown(self):
        i18n.set_language(self._saved)

    def test_default_language_is_english_until_bangla_rendering_is_verified(self):
        # See the note in i18n.py: flip to "bn" (and this test) only after
        # a Windows screenshot shows Bangla rendering correctly in Tk.
        self.assertEqual(i18n.DEFAULT_LANG, "en")
        self.assertIn("bn", i18n.LANGS)

    def test_t_returns_text_in_the_current_language(self):
        i18n.set_language("en")
        self.assertEqual(i18n.t("quick.button"), "Clean Now")
        i18n.set_language("bn")
        self.assertNotEqual(i18n.t("quick.button"), "Clean Now")

    def test_t_fills_placeholders(self):
        i18n.set_language("en")
        self.assertEqual(i18n.t("quick.done", freed="1.0 MB"), "1.0 MB of space freed.")

    def test_text_without_placeholders_is_not_formatted(self):
        # Literal braces in text must be safe when no kwargs are passed.
        with unittest.mock.patch.dict(i18n.STRINGS, {"x.braces": {"en": "a {b} c", "bn": "ক {b} খ"}}):
            i18n.set_language("en")
            self.assertEqual(i18n.t("x.braces"), "a {b} c")

    def test_unknown_key_returns_the_key_itself(self):
        self.assertEqual(i18n.t("no.such.key"), "no.such.key")

    def test_missing_language_falls_back_to_english(self):
        with unittest.mock.patch.dict(i18n.STRINGS, {"x.only_en": {"en": "English only"}}):
            i18n.set_language("bn")
            self.assertEqual(i18n.t("x.only_en"), "English only")

    def test_set_language_rejects_unknown_codes(self):
        i18n.set_language("en")
        self.assertFalse(i18n.set_language("fr"))
        self.assertEqual(i18n.get_language(), "en")

    def test_other_language(self):
        i18n.set_language("en")
        self.assertEqual(i18n.other_language(), "bn")
        i18n.set_language("bn")
        self.assertEqual(i18n.other_language(), "en")

    def test_category_helpers_fall_back_to_the_data_for_unknown_ids(self):
        cat = {"id": "fake_cat", "name": "Fake Name", "desc": "Fake desc"}
        i18n.set_language("bn")
        self.assertEqual(i18n.cat_name(cat), "Fake Name")
        self.assertEqual(i18n.cat_desc(cat), "Fake desc")


class TestEveryKeyTheGuiUsesExists(unittest.TestCase):
    def setUp(self):
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "pc_cleaner.py"), encoding="utf-8") as f:
            self.source = f.read()

    def _used_keys(self):
        prefixes = {k.split(".")[0] for k in i18n.STRINGS}
        literal = re.compile(r'"([a-z]+(?:\.[a-z0-9_]+)+)"')
        return {m for m in literal.findall(self.source) if m.split(".")[0] in prefixes}

    def test_every_key_used_in_the_gui_is_defined(self):
        missing = sorted(k for k in self._used_keys() if k not in i18n.STRINGS)
        self.assertEqual(missing, [], "keys used in pc_cleaner.py but missing from i18n.STRINGS")

    def test_every_non_category_key_is_actually_used(self):
        used = self._used_keys()
        unused = sorted(k for k in i18n.STRINGS if not k.startswith("cat.") and k not in used)
        self.assertEqual(unused, [], "dead strings in i18n.STRINGS")


if __name__ == "__main__":
    unittest.main()
