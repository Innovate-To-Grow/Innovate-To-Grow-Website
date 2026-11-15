from apps.authn.models import ContactEmail
from apps.authn.services.members.import_.review.analysis.choices import NEEDS_NAMES, NO_CHANGE_PERMISSION, PRIVILEGED
from apps.authn.tests.services.members.import_.conflicts.test_conflicts import not_privileged, options
from apps.authn.tests.services.members.import_.helpers import ImportTestCase, row


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
