import uuid

from apps.authn.models import ContactEmail
from apps.authn.services.members.import_.review.analysis import SKIP_EXISTING
from apps.authn.tests.services.members.import_.conflicts.test_conflicts import (
    NAME_DIFFERS,
    SKIP_MODE,
    UUID_HEADERS,
    options,
    uuid_row,
)
from apps.authn.tests.services.members.import_.helpers import ImportTestCase, row


class PrecedenceTests(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.work = self.email(self.ada, "ada.work@example.com", verified=True)

    def test_rows_with_c3_to_c5_are_never_grouped_as_repeats(self):
        bob = self.member("Bob", "Babbage", "bob@example.com")
        self.email(bob, "shared@example.com")
        ContactEmail.objects.create(member=None, email_address="Shared@example.com")
        rows = [
            uuid_row("shared@example.com", None),
            uuid_row("shared@example.com", None, Organization="X"),
            uuid_row("bob@example.com", self.ada.pk),
            uuid_row("bob@example.com", self.ada.pk, Organization="X"),
            uuid_row("ada@example.com", uuid.uuid4()),
            uuid_row("ada@example.com", uuid.uuid4(), Organization="X"),
        ]

        analyses = self.analyse(rows, UUID_HEADERS)

        self.assertEqual(
            [a.conflict for a in analyses],
            ["ambiguous_address"] * 2 + ["uuid_email_mismatch"] * 2 + ["uuid_not_found"] * 2,
        )
        self.assertEqual({tuple(a.facts["group"]) for a in analyses}, {()})

    def test_a_repeat_wins_over_a_differing_name(self):
        rows = [
            row("ada@example.com", Organization="X"),
            row("ada@example.com", First_Name="Grace", Last_Name="Hopper"),
        ]

        first, second = self.analyse(rows)

        self.assertEqual((first.conflict, second.conflict), ("duplicate_in_sheet", "duplicate_in_sheet"))
        self.assertTrue(options(first)["use_row"]["enabled"])
        self.assertEqual(options(second)["use_row"]["reason"], NAME_DIFFERS)
        self.assertFalse(options(second)["use_row"]["enabled"])
        self.assertEqual((second.facts["solo"], second.facts["solo_reason"]), (None, NAME_DIFFERS))

    def test_a_repeat_wins_over_a_secondary_address(self):
        first, second = self.analyse([row("ada@example.com"), row("ada.work@example.com", Organization="X")])

        self.assertEqual((first.conflict, second.conflict), ("duplicate_in_sheet", "duplicate_in_sheet"))
        self.assertEqual(first.facts["group"], [2, 3])
        self.assertEqual(
            options(second)["use_row"]["hint"], f"Apply this row: update Ada Lovelace (member {self.ada.pk})"
        )
        self.assertTrue(options(second)["use_row"]["enabled"])

    def test_a_repeat_wins_over_an_unlinked_address(self):
        ContactEmail.objects.create(member=None, email_address="loose@example.com")

        first, second = self.analyse([row("loose@example.com"), row("loose@example.com", Last_Name=None)])

        self.assertEqual((first.conflict, second.conflict), ("duplicate_in_sheet", "duplicate_in_sheet"))
        self.assertTrue(options(first)["use_row"]["enabled"])
        self.assertEqual(options(second)["use_row"]["reason"], "A new member needs a first and a last name")

    def test_a_repeat_wins_over_skip_mode_but_cannot_be_used_on_its_own(self):
        analyses = self.analyse([row("ada@example.com"), row("ada@example.com", Organization="X")], mode=SKIP_EXISTING)

        self.assertEqual({a.conflict for a in analyses}, {"duplicate_in_sheet"})
        self.assertEqual([options(a)["use_row"]["reason"] for a in analyses], [SKIP_MODE, SKIP_MODE])

    def test_a_repeat_of_a_secondary_address_in_skip_mode_cannot_be_used_on_its_own(self):
        rows = [row("ada.work@example.com"), row("ADA.WORK@example.com", Organization="X")]

        analyses = self.analyse(rows, mode=SKIP_EXISTING)

        self.assertEqual({a.conflict for a in analyses}, {"duplicate_in_sheet"})
        self.assertEqual([options(a)["use_row"]["reason"] for a in analyses], [SKIP_MODE, SKIP_MODE])

    def test_a_differing_name_comes_before_the_address_role(self):
        analysis = self.analyse_one(row("ada.work@example.com", First_Name="Grace", Last_Name="Hopper"))

        self.assertEqual((analysis.conflict, analysis.facts["matched_by"]), ("name_differs", "secondary"))

    def test_the_address_role_comes_before_skip_mode(self):
        analysis = self.analyse_one(row("ada.work@example.com"), mode=SKIP_EXISTING)

        self.assertEqual(analysis.conflict, "address_not_primary")

    def test_two_rows_naming_one_admin_are_a_repeat_like_any_other(self):
        self.member("Sam", "Admin", "sam@example.com", is_staff=True)
        sam = {"First_Name": "Sam", "Last_Name": "Admin"}

        first, second = self.analyse([row("sam@example.com", **sam), row("sam@example.com", Organization="X", **sam)])

        self.assertEqual((first.conflict, second.conflict), ("duplicate_in_sheet", "duplicate_in_sheet"))


class DuplicateInSheetTests(ImportTestCase):
    def test_the_same_address_twice_in_any_letter_case(self):
        rows = [row("ada@example.com", Organization="First"), row("ADA@Example.com", Organization="Second")]

        first, second = self.analyse(rows)

        label = f"Ada Lovelace (member {self.ada.pk})"
        for analysis in (first, second):
            with self.subTest(row=analysis.row_number):
                self.assertEqual((analysis.status, analysis.conflict), ("needs_decision", "duplicate_in_sheet"))
                self.assertEqual((analysis.default, analysis.facts["group"]), ("skip", [2, 3]))
                self.assertEqual(list(options(analysis)), ["use_row", "skip"])
                self.assertEqual(options(analysis)["use_row"]["hint"], f"Apply this row: update {label}")
                self.assertFalse(options(analysis)["use_row"]["suggested"])
                self.assertEqual(
                    options(analysis)["skip"]["hint"], "Skip this row; another row of the group may be used."
                )
                self.assertEqual(
                    analysis.facts["why"], f"Rows 2, 3 all resolve to {label}. Only one of them can be applied."
                )
        self.assertEqual(first.facts["solo"]["kind"], "update")
        self.assertEqual(first.facts["solo"]["target"], str(self.ada.pk))

    def test_the_same_new_address_twice(self):
        first, second = self.analyse([row("new@example.com"), row("New@Example.com", Organization="X")])

        self.assertEqual((first.conflict, second.conflict), ("duplicate_in_sheet", "duplicate_in_sheet"))
        self.assertEqual(options(first)["use_row"]["hint"], "Apply this row: create a new member with new@example.com")
        self.assertEqual(options(second)["use_row"]["hint"], "Apply this row: create a new member with New@Example.com")
        self.assertEqual(
            first.facts["why"], "Rows 2, 3 all resolve to new@example.com. Only one of them can be applied."
        )

    def test_the_same_member_uuid_with_different_addresses(self):
        rows = [uuid_row("ada.one@example.com", self.ada.pk), uuid_row("ada.two@example.com", self.ada.pk)]

        analyses = self.analyse(rows, UUID_HEADERS)

        self.assertEqual([(a.conflict, a.facts["group"]) for a in analyses], [("duplicate_in_sheet", [2, 3])] * 2)

    def test_three_rows_of_one_member_are_one_group(self):
        self.email(self.ada, "ada.old@example.com", "other")

        analyses = self.analyse([row("ada@example.com"), row("ada.old@example.com"), row("ADA@example.com")])

        self.assertEqual([a.facts["group"] for a in analyses], [[2, 3, 4]] * 3)

    def test_different_people_are_not_grouped(self):
        analyses = self.analyse([row("new@example.com"), row("ada@example.com"), row("other@example.com")])

        self.assertEqual([a.status for a in analyses], ["ready_create", "no_change", "ready_create"])
        self.assertEqual([a.facts["group"] for a in analyses], [[], [], []])

    def test_a_group_is_skipped_until_one_row_is_chosen(self):
        rows = [row("ada@example.com", Organization="First"), row("ada@example.com", Organization="Second")]

        outcomes = self.apply(rows)

        self.assertEqual([o.outcome for o in outcomes], ["skipped", "skipped"])
        self.ada.refresh_from_db()
        self.assertIsNone(self.ada.organization)

        outcomes = self.apply(rows, {3: ("use_row", [])})

        self.assertEqual([o.outcome for o in outcomes], ["skipped", "updated"])
        self.ada.refresh_from_db()
        self.assertEqual(self.ada.organization, "Second")
