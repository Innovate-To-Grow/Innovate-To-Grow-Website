"""Rows that name an Admin account, and rows whose address several members hold (C3).

An Admin account is matched and updated like any other member (C2, "a staff or superuser account", is retired): any
Admin may change any member. The import still never changes Admin access, whatever the sheet's Admin or Staff column
says, and the confirm page lists every change to an Admin account.
"""

from apps.authn.models import ContactEmail, Member
from apps.authn.services.members.import_.review.analysis.choices import NEEDS_NAMES, NO_CHANGE_PERMISSION
from apps.authn.tests.services.members.import_.conflicts.test_conflicts import options
from apps.authn.tests.services.members.import_.helpers import ImportTestCase, row


class AdminTargetTests(ImportTestCase):
    ADMIN_HEADERS = ["Primary Email", "First Name", "Last Name", "Admin"]

    def setUp(self):
        super().setUp()
        self.sam = self.member("Sam", "Admin", "sam@example.com", is_staff=True)
        self.admin_row = row("sam@example.com", First_Name="Sam", Last_Name="Admin", Organization="Admin Corp")

    def test_an_admin_account_gets_a_ready_row(self):
        analysis = self.analyse_one(self.admin_row)

        self.assertEqual((analysis.status, analysis.conflict, analysis.default), ("ready_update", "", "update"))

    def test_the_row_updates_the_admin_and_lists_the_change(self):
        (outcome,) = self.apply([self.admin_row])

        self.assertEqual(outcome.outcome, "updated")
        self.sam.refresh_from_db()
        self.assertEqual(self.sam.organization, "Admin Corp")
        self.assertEqual(
            outcome.listed["privileged_changes"],
            [f"Sam Admin (member {self.sam.pk}): Organization: '' → 'Admin Corp'"],
        )

    def test_an_ordinary_members_changes_are_not_listed_as_admin_changes(self):
        (outcome,) = self.apply([row("ada@example.com", Organization="Engines")])

        self.assertEqual(outcome.outcome, "updated")
        self.assertNotIn("privileged_changes", outcome.listed)

    def test_the_staff_column_never_changes_admin_access(self):
        demote = row("sam@example.com", First_Name="Sam", Last_Name="Admin", Staff="No")
        promote = row("ada@example.com", Staff="Yes")

        analyses = self.analyse([demote, promote])
        outcomes = self.apply([demote, promote], {2: ("update", [f"R8:{self.sam.pk}"]), 3: ("update", [])})

        self.assertEqual([a.risky for a in analyses], [{}, {}])
        self.assertEqual([o.outcome for o in outcomes], ["no_change", "no_change"])
        self.sam.refresh_from_db()
        self.ada.refresh_from_db()
        self.assertEqual((self.sam.is_staff, self.sam.is_superuser), (True, True))
        self.assertEqual((self.ada.is_staff, self.ada.is_superuser), (False, False))

    def test_an_admin_column_is_ignored_too(self):
        (outcome,) = self.apply([["ada@example.com", "Ada", "Lovelace", "Yes"]], headers=self.ADMIN_HEADERS)

        self.assertEqual(outcome.outcome, "no_change")
        self.assertFalse(Member.objects.get(pk=self.ada.pk).is_staff)


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
        sam = self.member("Sam", "Admin", "sam@example.com", is_staff=True)
        self.email(self.ada, "shared@example.com")
        self.email(sam, "Shared@example.com")

        refused = self.analyse_one(row("shared@example.com"), can_update=False)
        allowed = self.analyse_one(row("shared@example.com"))

        self.assertEqual({item["reason"] for item in refused.options[:2]}, {NO_CHANGE_PERMISSION})
        # An Admin account is offered like any other member.
        self.assertTrue(options(allowed)[f"use_member:{sam.pk}"]["enabled"])
        self.assertTrue(options(allowed)[f"use_member:{self.ada.pk}"]["enabled"])

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
