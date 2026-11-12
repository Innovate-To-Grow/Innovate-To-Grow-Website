"""Which member a row is about: the conflicts C1–C5, the precedence of all conflicts, and their default (Skip).

Every row that needs a decision starts on "skip"; the choice the import plan suggests is only marked. A choice that is
not allowed stays listed, disabled, with the reason.
"""

import uuid

from apps.authn.models import ContactEmail
from apps.authn.services.members.import_.review.analysis import SKIP_EXISTING
from apps.authn.services.members.import_.review.choices import NEEDS_NAMES, NO_CHANGE_PERMISSION, PRIVILEGED
from apps.authn.tests.services.members.import_.helpers import HEADERS, ImportTestCase, row

UUID_HEADERS = [*HEADERS, "Member UUID"]
NAME_DIFFERS = "The sheet's name differs from the member's; decide on this row alone"
SKIP_MODE = "The upload said to skip rows that match an existing member"


def uuid_row(primary, member_uuid, **cells):
    """A ``UUID_HEADERS`` row: ``row(primary, **cells)`` and its Member UUID cell."""
    return [*row(primary, **cells), str(member_uuid) if member_uuid else None]


def options(analysis) -> dict:
    return {item["value"]: item for item in analysis.options}


def not_privileged(member) -> bool:
    """``can_manage`` of an actor who is not an I2G Master."""
    return not (member.is_staff or member.is_superuser)


class ConflictCatalogueTests(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.grace = self.member("Grace", "Hopper", "grace@example.com")
        self.bob = self.member("Bob", "Babbage", "bob@example.com")
        self.sam = self.member("Sam", "Staff", "sam@example.com", is_staff=True)
        self.email(self.bob, "bob.work@example.com", verified=True)
        self.email(self.grace, "shared@example.com", "other")
        ContactEmail.objects.create(member=None, email_address="SHARED@example.com")
        self.loose = ContactEmail.objects.create(member=None, email_address="loose@example.com")

    def test_each_conflict_is_detected_and_every_one_starts_on_skip(self):
        rows = [
            uuid_row("twin@example.com", None),
            uuid_row("twin@example.com", None, Organization="Twin Corp"),
            uuid_row("sam@example.com", None, First_Name="Sam", Last_Name="Staff"),
            uuid_row("shared@example.com", None),
            uuid_row("bob@example.com", self.ada.pk, First_Name="Bob", Last_Name="Babbage"),
            uuid_row("ghost@example.com", uuid.uuid4()),
            uuid_row("grace@example.com", None, First_Name="Someone", Last_Name="Else"),
            uuid_row("bob.work@example.com", None, First_Name="Bob", Last_Name="Babbage"),
            uuid_row("loose@example.com", None, First_Name="Lin", Last_Name="Loose"),
            uuid_row("ada@example.com", None),
        ]

        analyses = self.analyse(rows, UUID_HEADERS, mode=SKIP_EXISTING, can_manage=not_privileged)

        self.assertEqual(
            {a.row_number: a.conflict for a in analyses},
            {
                2: "duplicate_in_sheet",
                3: "duplicate_in_sheet",
                4: "privileged_target",
                5: "ambiguous_address",
                6: "uuid_email_mismatch",
                7: "uuid_not_found",
                8: "name_differs",
                9: "address_not_primary",
                10: "unlinked_address",
                11: "exists_but_skip_mode",
            },
        )
        self.assertEqual({a.status for a in analyses}, {"needs_decision"})
        self.assertEqual({a.default for a in analyses}, {"skip"})
        for analysis in analyses:
            with self.subTest(row=analysis.row_number):
                self.assertTrue(options(analysis)["skip"]["enabled"])
        suggested = {(a.row_number, o["value"]) for a in analyses for o in a.options if o["suggested"]}
        self.assertEqual(suggested, {(9, "update"), (10, f"create_claim:{self.loose.pk}")})

    def test_ready_rows_default_to_their_action(self):
        analyses = self.analyse([row("new@example.com"), row("ada@example.com", Organization="Engines")])

        self.assertEqual(
            [(a.status, a.default) for a in analyses], [("ready_create", "create"), ("ready_update", "update")]
        )
        self.assertEqual([list(options(a)) for a in analyses], [["create", "skip"], ["update", "skip"]])
        self.assertEqual(analyses[1].options[0]["label"], f"Update Ada Lovelace (member {self.ada.pk})")
        self.assertEqual(analyses[1].facts["matched_by"], "primary")


class PrecedenceTests(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.work = self.email(self.ada, "ada.work@example.com", verified=True)

    def test_rows_with_c2_to_c5_are_never_grouped_as_repeats(self):
        bob = self.member("Bob", "Babbage", "bob@example.com")
        self.member("Sam", "Staff", "sam@example.com", is_staff=True)
        self.email(bob, "shared@example.com")
        ContactEmail.objects.create(member=None, email_address="Shared@example.com")
        staff = {"First_Name": "Sam", "Last_Name": "Staff"}
        rows = [
            uuid_row("sam@example.com", None, **staff),
            uuid_row("sam@example.com", None, Organization="Staff Corp", **staff),
            uuid_row("shared@example.com", None),
            uuid_row("shared@example.com", None, Organization="X"),
            uuid_row("bob@example.com", self.ada.pk),
            uuid_row("bob@example.com", self.ada.pk, Organization="X"),
            uuid_row("ada@example.com", uuid.uuid4()),
            uuid_row("ada@example.com", uuid.uuid4(), Organization="X"),
        ]

        analyses = self.analyse(rows, UUID_HEADERS, can_manage=not_privileged)

        self.assertEqual(
            [a.conflict for a in analyses],
            ["privileged_target"] * 2
            + ["ambiguous_address"] * 2
            + ["uuid_email_mismatch"] * 2
            + ["uuid_not_found"] * 2,
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

    def test_permission_comes_before_the_name_and_the_role(self):
        sam = self.member("Sam", "Staff", "sam@example.com", is_staff=True)
        self.email(sam, "sam.work@example.com")

        for cells_row in (row("sam@example.com"), row("sam.work@example.com", First_Name="Sam", Last_Name="Staff")):
            with self.subTest(primary=cells_row[0]):
                analysis = self.analyse_one(cells_row, can_manage=not_privileged, mode=SKIP_EXISTING)
                self.assertEqual(analysis.conflict, "privileged_target")


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


class PrivilegedTargetTests(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.sam = self.member("Sam", "Staff", "sam@example.com", is_staff=True)
        self.staff_row = row("sam@example.com", First_Name="Sam", Last_Name="Staff", Organization="Staff Corp")

    def test_a_staff_account_offers_only_skip(self):
        analysis = self.analyse_one(self.staff_row, can_manage=not_privileged)

        self.assertEqual(
            (analysis.status, analysis.conflict, analysis.default), ("needs_decision", "privileged_target", "skip")
        )
        self.assertEqual(
            analysis.options,
            [
                {
                    "value": "skip",
                    "label": "Skip this row",
                    "hint": PRIVILEGED,
                    "enabled": True,
                    "reason": "",
                    "suggested": False,
                }
            ],
        )
        self.assertEqual(
            analysis.facts["why"],
            f"You do not have permission to update Sam Staff (member {self.sam.pk}) (only an I2G Master may change "
            "staff and superuser accounts).",
        )

    def test_a_superuser_account_too(self):
        self.member("Root", "User", "root@example.com", is_staff=True, is_superuser=True)

        analysis = self.analyse_one(
            row("root@example.com", First_Name="Root", Last_Name="User"), can_manage=not_privileged
        )

        self.assertEqual(analysis.conflict, "privileged_target")

    def test_an_i2g_master_gets_a_ready_row(self):
        analysis = self.analyse_one(self.staff_row, is_master=True)

        self.assertEqual((analysis.status, analysis.conflict), ("ready_update", ""))

    def test_the_skipped_row_changes_nothing(self):
        (outcome,) = self.apply([self.staff_row], can_manage=not_privileged)

        self.assertEqual(outcome.outcome, "skipped")
        self.assertIn("You do not have permission to update Sam Staff", outcome.reason)
        self.sam.refresh_from_db()
        self.assertIsNone(self.sam.organization)


class AmbiguousAddressTests(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.grace = self.member("Grace", "Hopper", "grace@example.com")

    def test_two_members_hold_the_address_in_different_letter_case(self):
        self.email(self.ada, "shared@example.com")
        self.email(self.grace, "SHARED@example.com", "other")

        analysis = self.analyse_one(row("shared@example.com"))

        self.assertEqual(
            (analysis.status, analysis.conflict, analysis.default), ("needs_decision", "ambiguous_address", "skip")
        )
        by_value = options(analysis)
        self.assertEqual(set(by_value), {f"use_member:{self.ada.pk}", f"use_member:{self.grace.pk}", "skip"})
        self.assertEqual(analysis.options[-1]["value"], "skip")
        self.assertEqual(
            by_value[f"use_member:{self.ada.pk}"]["label"],
            f"Use Ada Lovelace (member {self.ada.pk}) (shared@example.com)",
        )
        self.assertEqual(
            by_value[f"use_member:{self.grace.pk}"]["label"],
            f"Use Grace Hopper (member {self.grace.pk}) (SHARED@example.com)",
        )
        self.assertTrue(all(item["enabled"] and not item["suggested"] for item in analysis.options))
        self.assertIsNone(analysis.target)
        self.assertIn("matches 2 contact emails that differ only in letter case", analysis.facts["why"])

    def test_the_unlinked_variant_cannot_be_claimed_while_another_belongs_to_a_member(self):
        loose = ContactEmail.objects.create(member=None, email_address="Shared@example.com")
        self.email(self.ada, "shared@example.com")

        analysis = self.analyse_one(row("shared@example.com"))

        claim = options(analysis)[f"create_claim:{loose.pk}"]
        self.assertEqual(claim["label"], "Claim the unlinked record Shared@example.com for a new member")
        self.assertEqual(
            (claim["enabled"], claim["reason"]),
            (False, "Another record of this address belongs to a member; merge the duplicates first"),
        )
        self.assertTrue(options(analysis)[f"use_member:{self.ada.pk}"]["enabled"])

    def test_unlinked_variants_can_be_claimed_by_a_row_with_both_names(self):
        first = ContactEmail.objects.create(member=None, email_address="loose@example.com")
        second = ContactEmail.objects.create(member=None, email_address="LOOSE@example.com")

        named = self.analyse_one(row("loose@example.com"))
        unnamed = self.analyse_one(row("loose@example.com", Last_Name=None))

        values = [f"create_claim:{first.pk}", f"create_claim:{second.pk}"]
        self.assertEqual(set(options(named)), {*values, "skip"})
        self.assertTrue(all(options(named)[value]["enabled"] for value in values))
        self.assertEqual({options(unnamed)[value]["reason"] for value in values}, {NEEDS_NAMES})

    def test_using_a_member_needs_permission(self):
        sam = self.member("Sam", "Staff", "sam@example.com", is_staff=True)
        self.email(self.ada, "shared@example.com")
        self.email(sam, "Shared@example.com")

        refused = self.analyse_one(row("shared@example.com"), can_update=False)
        not_master = self.analyse_one(row("shared@example.com"), can_manage=not_privileged)

        self.assertEqual({item["reason"] for item in refused.options[:2]}, {NO_CHANGE_PERMISSION})
        self.assertEqual(options(not_master)[f"use_member:{sam.pk}"]["reason"], PRIVILEGED)
        self.assertTrue(options(not_master)[f"use_member:{self.ada.pk}"]["enabled"])

    def test_no_member_is_picked_silently_and_a_choice_updates_only_that_member(self):
        self.email(self.ada, "shared@example.com")
        self.email(self.grace, "SHARED@example.com")
        cells_row = row("shared@example.com", First_Name="Grace", Last_Name="Hopper", Organization="Navy")

        (skipped,) = self.apply([cells_row])
        (chosen,) = self.apply([cells_row], {2: (f"use_member:{self.grace.pk}", [])})

        self.assertEqual((skipped.outcome, chosen.outcome), ("skipped", "updated"))
        self.grace.refresh_from_db()
        self.ada.refresh_from_db()
        self.assertEqual((self.grace.organization, self.ada.organization), ("Navy", None))


class UuidMismatchTests(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.grace = self.member("Grace", "Hopper", "grace@example.com")

    def test_the_member_uuid_and_the_primary_email_name_different_members(self):
        analysis = self.analyse_one(uuid_row("grace@example.com", self.ada.pk), UUID_HEADERS)

        self.assertEqual(
            (analysis.status, analysis.conflict, analysis.default), ("needs_decision", "uuid_email_mismatch", "skip")
        )
        self.assertEqual(
            (analysis.facts["uuid_member"], analysis.facts["email_member"]), (str(self.ada.pk), str(self.grace.pk))
        )
        self.assertIsNone(analysis.target)
        self.assertEqual(list(options(analysis)), [f"use_member:{self.ada.pk}", f"use_member:{self.grace.pk}", "skip"])
        self.assertEqual(
            [item["label"] for item in analysis.options[:2]],
            [
                f"Use Ada Lovelace (member {self.ada.pk}) (by Member UUID); don't give them the address",
                f"Use Grace Hopper (member {self.grace.pk}) (by email)",
            ],
        )
        self.assertTrue(all(item["enabled"] for item in analysis.options))
        self.assertEqual(
            analysis.facts["why"],
            f"The Member UUID names Ada Lovelace (member {self.ada.pk}), but grace@example.com is the primary email of "
            f"Grace Hopper (member {self.grace.pk}).",
        )

    def test_the_address_may_have_any_role(self):
        self.email(self.grace, "grace.work@example.com")

        analysis = self.analyse_one(uuid_row("grace.work@example.com", self.ada.pk), UUID_HEADERS)

        self.assertEqual(analysis.conflict, "uuid_email_mismatch")
        self.assertIn("the secondary email of Grace Hopper", analysis.facts["why"])

    def test_each_member_is_offered_only_with_permission(self):
        sam = self.member("Sam", "Staff", "sam@example.com", is_staff=True)

        analysis = self.analyse_one(uuid_row("sam@example.com", self.ada.pk), UUID_HEADERS, can_manage=not_privileged)

        self.assertEqual(options(analysis)[f"use_member:{sam.pk}"]["reason"], PRIVILEGED)
        self.assertTrue(options(analysis)[f"use_member:{self.ada.pk}"]["enabled"])

    def test_using_the_uuid_member_never_gives_them_the_address(self):
        cells_row = uuid_row("grace@example.com", self.ada.pk, Organization="Engines", Primary_Verified="TRUE")

        (outcome,) = self.apply([cells_row], {2: (f"use_member:{self.ada.pk}", [])}, UUID_HEADERS)

        self.assertEqual(outcome.outcome, "updated")
        self.ada.refresh_from_db()
        self.assertEqual(self.ada.organization, "Engines")
        self.assertEqual(ContactEmail.objects.get(email_address="grace@example.com").member, self.grace)
        self.assertIn(
            f"Primary Email grace@example.com belongs to Grace Hopper (member {self.grace.pk}); it is not added to Ada "
            f"Lovelace (member {self.ada.pk}), and its Verified/Subscribed cells are ignored",
            outcome.notes,
        )


class UuidNotFoundTests(ImportTestCase):
    def test_a_member_uuid_that_matches_nobody(self):
        unknown = uuid.uuid4()

        analysis = self.analyse_one(uuid_row("ada@example.com", unknown, Organization="X"), UUID_HEADERS)

        self.assertEqual(
            (analysis.status, analysis.conflict, analysis.default), ("needs_decision", "uuid_not_found", "skip")
        )
        self.assertEqual(list(options(analysis)), ["ignore_uuid", "skip"])
        ignore = options(analysis)["ignore_uuid"]
        self.assertTrue(ignore["enabled"])
        self.assertEqual(ignore["hint"], f"The row would update Ada Lovelace (member {self.ada.pk})")
        self.assertEqual(
            (analysis.facts["fallback"]["kind"], analysis.facts["fallback"]["target"]), ("update", str(self.ada.pk))
        )
        self.assertEqual(
            analysis.facts["why"],
            f"No member has the Member UUID {unknown}: it may be a deleted member, a typo, or a sheet exported from "
            "another site (such as staging).",
        )

    def test_matched_by_email_the_row_would_create_a_member(self):
        analysis = self.analyse_one(uuid_row("ghost@example.com", uuid.uuid4()), UUID_HEADERS)

        self.assertEqual(
            options(analysis)["ignore_uuid"]["hint"], "The row would create a new member with ghost@example.com"
        )

    def test_ignoring_the_uuid_is_disabled_when_the_email_match_would_be_skipped(self):
        cases = [
            (uuid_row("ada@example.com", uuid.uuid4(), First_Name="Grace", Last_Name="Hopper"), {}, NAME_DIFFERS),
            (uuid_row("ghost@example.com", uuid.uuid4(), Last_Name=None), {}, "Missing last name"),
            (uuid_row("ada@example.com", uuid.uuid4()), {"mode": SKIP_EXISTING}, SKIP_MODE),
        ]
        for cells_row, context, reason in cases:
            with self.subTest(reason=reason):
                analysis = self.analyse_one(cells_row, UUID_HEADERS, **context)
                self.assertEqual(analysis.conflict, "uuid_not_found")
                self.assertEqual(
                    (options(analysis)["ignore_uuid"]["enabled"], options(analysis)["ignore_uuid"]["reason"]),
                    (False, reason),
                )

    def test_text_that_is_not_a_uuid(self):
        analysis = self.analyse_one(uuid_row("ada@example.com", "abc-123"), UUID_HEADERS)

        self.assertEqual(analysis.conflict, "uuid_not_found")
        self.assertEqual(analysis.facts["why"], "The Member UUID cell 'abc-123' is not a UUID.")

    def test_ignoring_the_uuid_applies_the_email_match(self):
        cells_row = uuid_row("ada@example.com", uuid.uuid4(), Organization="Engines")

        (outcome,) = self.apply([cells_row], {2: ("ignore_uuid", [])}, UUID_HEADERS)

        self.assertEqual(outcome.outcome, "updated")
        self.ada.refresh_from_db()
        self.assertEqual(self.ada.organization, "Engines")

    def test_a_member_uuid_match_skips_the_name_check(self):
        analysis = self.analyse_one(
            uuid_row("ada@example.com", self.ada.pk, First_Name="Augusta", Last_Name="King"), UUID_HEADERS
        )

        self.assertEqual(
            (analysis.status, analysis.conflict, analysis.facts["matched_by"]), ("ready_update", "", "uuid")
        )
