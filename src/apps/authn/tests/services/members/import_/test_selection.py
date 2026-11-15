"""What blocks applying a review's choices (``selection_problems``), and the confirm page's counts (``summarize``)."""

import uuid

from apps.authn.models import ContactEmail
from apps.authn.services.members.import_.review.actions import Action, resolve_action
from apps.authn.services.members.import_.review.describe import conflict_code, conflict_title, describe_action, why
from apps.authn.services.members.import_.review.lookup import Snapshot
from apps.authn.services.members.import_.review.selection import (
    ForgedSelection,
    clean_selection,
    selection_problems,
    summarize,
)
from apps.authn.tests.services.members.import_.helpers import HEADERS, ImportTestCase, row

UUID_HEADERS = [*HEADERS, "Member UUID"]


class SelectionProblemTests(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.ada_label = f"Ada Lovelace (member {self.ada.pk})"

    def test_the_default_choices_have_no_problems(self):
        self.email(self.ada, "ada.work@example.com", verified=True)
        rows = [row("ada.work@example.com"), row("new@example.com"), row("twin@example.com"), row("twin@example.com")]

        self.assertEqual(selection_problems(self.analyse([*rows, row(None)]), {}), [])

    def test_two_rows_that_change_one_member(self):
        grace = self.member("Grace", "Hopper", "grace@example.com")
        rows = [
            [*row("grace@example.com", First_Name="Grace", Last_Name="Hopper", Organization="Navy"), None],
            [*row("grace@example.com"), str(self.ada.pk)],
        ]
        analyses = self.analyse(rows, UUID_HEADERS)
        self.assertEqual([a.conflict for a in analyses], ["", "uuid_email_mismatch"])

        problems = selection_problems(analyses, {3: (f"use_member:{grace.pk}", [])})

        self.assertEqual(
            problems,
            [
                f"Rows 2 and 3 would all change Grace Hopper (member {grace.pk}). Choose one of them and skip the "
                "others."
            ],
        )
        self.assertEqual(selection_problems(analyses, {3: (f"use_member:{self.ada.pk}", [])}), [])

    def test_two_rows_of_a_repeat_group_both_used(self):
        analyses = self.analyse([row("ada@example.com", Organization="A"), row("ADA@example.com", Organization="B")])

        problems = selection_problems(analyses, {2: ("use_row", []), 3: ("use_row", [])})

        self.assertEqual(
            problems,
            [
                f"Rows 2 and 3 would all change {self.ada_label}. Choose one of them and skip the others.",
                "Rows 2 and 3 are the same person; use only one of them (rows 2 and 3).",
            ],
        )
        self.assertEqual(selection_problems(analyses, {2: ("skip", []), 3: ("use_row", [])}), [])

    def test_three_rows_of_one_new_member_all_used(self):
        analyses = self.analyse([row("new@example.com"), row("NEW@example.com"), row("new@EXAMPLE.com")])

        problems = selection_problems(analyses, {number: ("use_row", []) for number in (2, 3, 4)})

        self.assertEqual(problems, ["Rows 2, 3 and 4 are the same person; use only one of them (rows 2, 3 and 4)."])

    def test_one_unlinked_record_claimed_by_two_rows(self):
        ContactEmail.objects.create(member=None, email_address="loose@example.com")
        analyses = self.analyse([row("loose@example.com"), row("loose@example.com", Organization="X")])

        problems = selection_problems(analyses, {2: ("use_row", []), 3: ("use_row", [])})

        self.assertEqual(
            problems,
            [
                "Rows 2 and 3 would all change the contact email loose@example.com. Choose one of them and skip the "
                "others.",
                "Rows 2 and 3 are the same person; use only one of them (rows 2 and 3).",
            ],
        )

    def test_a_promotion_of_an_address_ticked_to_be_unverified(self):
        work = self.email(self.ada, "ada.work@example.com", verified=True)
        analyses = self.analyse([row("ada.work@example.com", Primary_Verified="FALSE")])
        self.assertTrue(next(i for i in analyses[0].risky[str(self.ada.pk)] if i["id"] == f"R6:{work.pk}")["enabled"])

        problems = selection_problems(analyses, {2: ("update_make_primary", [f"R6:{work.pk}"])})

        self.assertEqual(
            problems,
            [
                "Row 2: ada.work@example.com can't be made the primary email while it is unverified; untick its "
                "un-verify box"
            ],
        )

    def test_rows_that_cannot_be_imported_are_left_out(self):
        analyses = self.analyse([row(None), row("not-an-email")])

        self.assertEqual(selection_problems(analyses, {2: ("create", []), 3: ("create", [])}), [])


class CleanSelectionTests(ImportTestCase):
    def test_a_missing_choice_is_the_default(self):
        (analysis,) = self.analyse([row("new@example.com")])

        self.assertEqual(clean_selection(analysis, None, []), ("create", []))
        self.assertEqual(clean_selection(analysis, "", ()), ("create", []))

    def test_a_repeated_tick_is_kept_once(self):
        work = self.email(self.ada, "ada.work@example.com")
        (analysis,) = self.analyse([row("ada@example.com")])
        tick = f"R1:{work.pk}"

        self.assertEqual(clean_selection(analysis, "update", [tick, tick]), ("update", [tick]))

    def test_an_invalid_row_is_always_skipped(self):
        (analysis,) = self.analyse([row(None)])

        self.assertEqual(clean_selection(analysis, "create", [f"R1:{uuid.uuid4()}"]), ("skip", []))

    def test_a_forged_choice(self):
        (analysis,) = self.analyse([row("new@example.com")])

        with self.assertRaisesMessage(ForgedSelection, "Row 2: 'update' is not one of this row's choices"):
            clean_selection(analysis, "update", [])


class SummaryTests(ImportTestCase):
    def test_counts_rows_decisions_and_the_risky_changes_spelled_out(self):
        work = self.email(self.ada, "ada.work@example.com")
        self.member("Grace", "Hopper", "grace@example.com")
        rows = [
            row("ada@example.com", Organization="Engines"),
            row("grace@example.com", First_Name="Someone", Last_Name="Else"),
            row("new@example.com"),
            row(None),
        ]
        analyses = self.analyse(rows)
        selections = {2: ("update", [f"R1:{work.pk}"]), 3: ("update_keep_name", [])}

        summary = summarize(analyses, selections)

        self.assertEqual(summary["rows"], {"updated": 1, "no_change": 1, "created": 1, "not_imported": 1})
        self.assertEqual(summary["decisions"], {"name_differs": {"update_keep_name": 1}})
        self.assertEqual(summary["listed"], {"emails_deleted": ["Row 2: secondary ada.work@example.com"]})

    def test_the_defaults(self):
        self.email(self.ada, "ada.work@example.com")
        analyses = self.analyse([row("ada.work@example.com"), row("new@example.com"), row("ada@example.com")])

        summary = summarize(analyses, {})

        self.assertEqual(summary["rows"], {"skipped": 2, "created": 1})
        self.assertEqual(summary["decisions"], {"duplicate_in_sheet": {"skip": 2}})
        self.assertEqual(summary["listed"], {})


class ActionTests(ImportTestCase):
    def test_each_choice_resolves_to_its_action(self):
        solo = {"kind": "create", "target": None, "keep_name": False, "make_primary": False, "claim": None}
        facts = {"target": "m1", "record": "r1", "solo": solo, "fallback": None}
        cases = {
            "skip": Action("skip"),
            "": Action("skip"),
            "create": Action("create"),
            "update": Action("update", target="m1"),
            "update_same_person": Action("update", target="m1"),
            "update_keep_name": Action("update", target="m1", keep_name=True),
            "update_make_primary": Action("update", target="m1", make_primary=True),
            "use_row": Action("create"),
            "ignore_uuid": Action("skip"),
            "use_member:m2": Action("update", target="m2"),
            "create_claim:r9": Action("create_claim", claim="r9"),
            "attach_to:m3": Action("update", target="m3", keep_name=True, claim="r1"),
            "frobnicate:x": Action("skip"),
        }
        for choice, action in cases.items():
            with self.subTest(choice=choice):
                self.assertEqual(resolve_action(choice, facts), action)

    def test_conflicts_and_actions_in_words(self):
        snapshot = Snapshot()

        self.assertEqual(
            (conflict_code("address_not_primary"), conflict_title("address_not_primary")),
            ("C7", "The address is a member's secondary or other email"),
        )
        self.assertEqual((conflict_code(""), conflict_title("unknown")), ("", ""))
        self.assertEqual(why("", {}, snapshot), "")
        self.assertEqual(
            [describe_action(action, snapshot, {}) for action in (None, Action("skip"), Action("update", target="x"))],
            ["skip it", "skip it", "update the member"],
        )
