"""The name rule: when a sheet's name and a member's name can be the same person, and when it is a decision (C6)."""

from apps.authn.services.members.import_.review.names import names_agree, normalize_name
from apps.authn.tests.services.members.import_.helpers import HEADERS, ImportTestCase, row


class NormalizeNameTests(ImportTestCase):
    def test_accents_case_punctuation_and_spaces(self):
        cases = {
            "  José-María  O'Neil ": "jose maria oneil",
            "St. John, Jr.": "st john jr",
            "O’Brien": "obrien",
            "ÅNGSTRÖM": "angstrom",
            "Straße": "strasse",
            "ＡＤＡ": "ada",
            "Anne -- Marie": "anne marie",
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(normalize_name(name), expected)

    def test_blank_names(self):
        self.assertEqual([normalize_name(None), normalize_name(""), normalize_name(" . ")], ["", "", ""])


class FirstNameTests(ImportTestCase):
    def test_a_first_name_agrees_with_its_prefix(self):
        pairs = [
            ("Chris", "Christopher"),
            ("Christopher", "Chris"),
            ("C.", "Christopher"),
            ("J", "John"),
            ("Mary-Jane", "Mary Jane"),
            ("MaryJane", "Mary-Jane"),
            ("ada", "ADA"),
        ]
        for sheet, stored in pairs:
            with self.subTest(sheet=sheet, stored=stored):
                self.assertTrue(names_agree(sheet, "Lovelace", stored, "Lovelace"))

    def test_other_first_names_do_not_agree(self):
        for sheet, stored in [("Bob", "Robert"), ("Christina", "Christopher"), ("Jon", "John")]:
            with self.subTest(sheet=sheet, stored=stored):
                self.assertFalse(names_agree(sheet, "Lovelace", stored, "Lovelace"))


class LastNameTests(ImportTestCase):
    def test_double_barrelled_last_names(self):
        pairs = [
            ("Smith", "Smith-Jones"),
            ("Jones", "Smith Jones"),
            ("Smith-Jones", "Smith"),
            ("SmithJones", "Smith-Jones"),
            ("Lovelace-Byron", "Byron"),
        ]
        for sheet, stored in pairs:
            with self.subTest(sheet=sheet, stored=stored):
                self.assertTrue(names_agree("Ada", sheet, "Ada", stored))

    def test_a_last_name_is_not_matched_by_its_prefix(self):
        for sheet, stored in [("Smit", "Smith"), ("Love", "Lovelace"), ("Jones", "Smith")]:
            with self.subTest(sheet=sheet, stored=stored):
                self.assertFalse(names_agree("Ada", sheet, "Ada", stored))


class AccentsAndPunctuationTests(ImportTestCase):
    def test_names_that_differ_only_in_accents_case_or_punctuation_agree(self):
        cases = [
            ("JOSÉ", "GARCÍA", "jose", "garcia"),
            ("Zoë", "O'Brien", "Zoe", "OBrien"),
            ("Ada", "D’Arcy", "Ada", "d'arcy"),
            ("Ada", "St. John", "ada", "st john"),
        ]
        for case in cases:
            with self.subTest(case=case):
                self.assertTrue(names_agree(*case))


class BlankNameTests(ImportTestCase):
    def test_a_blank_name_on_either_side_is_never_a_mismatch(self):
        cases = [
            ("", "", "Ada", "Lovelace"),
            ("Ada", "", "Ada", "Lovelace"),
            ("", "Lovelace", "Ada", "Lovelace"),
            ("Grace", "Hopper", "", ""),
            ("Ada", None, "Ada", "Lovelace"),
            ("  ", " ", "Ada", "Lovelace"),
        ]
        for case in cases:
            with self.subTest(case=case):
                self.assertTrue(names_agree(*case))

    def test_the_other_name_is_still_compared(self):
        self.assertFalse(names_agree("Grace", "", "Ada", "Lovelace"))
        self.assertFalse(names_agree("", "Hopper", "Ada", "Lovelace"))

    def test_both_names_must_agree(self):
        self.assertFalse(names_agree("Ada", "Byron", "Ada", "Lovelace"))
        self.assertFalse(names_agree("Grace", "Lovelace", "Ada", "Lovelace"))


class NameCheckInTheReviewTests(ImportTestCase):
    def test_a_compatible_name_updates_without_a_decision(self):
        analysis = self.analyse_one(row("ada@example.com", First_Name="ADA", Last_Name="Lovelace-Byron"))

        self.assertEqual((analysis.status, analysis.conflict), ("ready_update", ""))
        self.assertEqual(analysis.default, "update")

    def test_a_different_name_needs_a_decision(self):
        analysis = self.analyse_one(row("ada@example.com", First_Name="Grace", Last_Name="Hopper"))

        self.assertEqual(
            (analysis.status, analysis.conflict, analysis.default), ("needs_decision", "name_differs", "skip")
        )
        self.assertEqual(
            analysis.facts["why"],
            f"ada@example.com is the primary email of Ada Lovelace (member {self.ada.pk}). The sheet names 'Grace "
            "Hopper', but the member is 'Ada Lovelace'.",
        )

    def test_blank_name_cells_never_need_a_decision(self):
        analysis = self.analyse_one(row("ada@example.com", First_Name=None, Last_Name=None))

        self.assertEqual((analysis.status, analysis.conflict), ("no_change", ""))

    def test_a_member_without_a_stored_name_takes_the_sheet_name(self):
        self.member("", "", "nameless@example.com")

        analysis = self.analyse_one(row("nameless@example.com", First_Name="Grace", Last_Name="Hopper"))

        self.assertEqual((analysis.status, analysis.conflict), ("ready_update", ""))

    def test_middle_names_are_not_compared(self):
        headers = [*HEADERS, "Middle Name"]

        analysis = self.analyse_one([*row("ada@example.com"), "Augusta"], headers)

        self.assertEqual((analysis.status, analysis.conflict), ("ready_update", ""))
