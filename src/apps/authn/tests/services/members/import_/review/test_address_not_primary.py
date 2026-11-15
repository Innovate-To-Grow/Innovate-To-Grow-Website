from django.core import mail

from apps.authn.models import ContactEmail
from apps.authn.services.members.import_.review.analysis.choices import NO_CHANGE_PERMISSION
from apps.authn.tests.services.members.import_.conflicts.test_conflicts_matched import (
    UNVERIFIED,
    UUID_HEADERS,
    options,
    roles,
    uuid_row,
)
from apps.authn.tests.services.members.import_.helpers import ImportTestCase, row


class AddressNotPrimaryTests(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.label = f"Ada Lovelace (member {self.ada.pk})"
        self.work = self.email(self.ada, "ada.work@example.com", verified=True, subscribe=True)

    def test_the_address_is_the_members_secondary(self):
        analysis = self.analyse_one(row("ada.work@example.com"))

        self.assertEqual(
            (analysis.status, analysis.conflict, analysis.default), ("needs_decision", "address_not_primary", "skip")
        )
        self.assertEqual(
            (analysis.target, analysis.facts["matched_by"], analysis.facts["record"]),
            (str(self.ada.pk), "secondary", str(self.work.pk)),
        )
        self.assertEqual(list(options(analysis)), ["update", "update_make_primary", "skip"])
        update, promote = analysis.options[:2]
        self.assertEqual(update["label"], f"Update {self.label}; keep the email roles")
        self.assertEqual(
            update["hint"], "The flag cells apply to ada.work@example.com; the primary ada@example.com is kept."
        )
        self.assertEqual((update["enabled"], update["suggested"]), (True, True))
        self.assertEqual(promote["label"], f"Update {self.label} and make ada.work@example.com their primary")
        self.assertEqual((promote["enabled"], promote["suggested"]), (True, False))
        self.assertEqual(
            analysis.facts["why"],
            f"ada.work@example.com is the secondary email of {self.label}, whose primary email is ada@example.com.",
        )

    def test_an_other_address_too(self):
        self.email(self.ada, "ada.old@example.com", "other")

        analysis = self.analyse_one(row("ada.old@example.com"))

        self.assertEqual((analysis.conflict, analysis.facts["matched_by"]), ("address_not_primary", "other"))

    def test_making_an_unverified_address_primary_is_disabled(self):
        ContactEmail.objects.filter(pk=self.work.pk).update(verified=False)

        analysis = self.analyse_one(row("ada.work@example.com"))

        self.assertTrue(options(analysis)["update"]["enabled"])
        self.assertEqual(
            (options(analysis)["update_make_primary"]["enabled"], options(analysis)["update_make_primary"]["reason"]),
            (False, UNVERIFIED),
        )

    def test_updating_needs_permission(self):
        analysis = self.analyse_one(row("ada.work@example.com"), can_update=False)

        self.assertEqual(
            [item["reason"] for item in analysis.options], [NO_CHANGE_PERMISSION, NO_CHANGE_PERMISSION, ""]
        )

    def test_a_member_uuid_whose_member_owns_the_address_as_secondary(self):
        analysis = self.analyse_one(uuid_row("ada.work@example.com", self.ada.pk), UUID_HEADERS)

        self.assertEqual((analysis.conflict, analysis.facts["matched_by"]), ("address_not_primary", "uuid"))

    def test_row5_update_keeps_every_address_and_its_role(self):
        cells_row = row(
            "ada.work@example.com", Organization="Spirit", Primary_Verified="TRUE", Primary_Subscribed="FALSE"
        )

        (outcome,) = self.apply([cells_row], {2: ("update", [])})

        self.assertEqual(outcome.outcome, "updated")
        self.ada.refresh_from_db()
        self.assertEqual(self.ada.organization, "Spirit")
        self.assertEqual(roles(self.ada), {"ada@example.com": "primary", "ada.work@example.com": "secondary"})
        self.work.refresh_from_db()
        primary = ContactEmail.objects.get(email_address="ada@example.com")
        self.assertEqual((self.work.verified, self.work.subscribe), (True, False))
        self.assertEqual((primary.verified, primary.subscribe), (True, True))
        self.assertEqual(mail.outbox, [])

    def test_the_flag_cells_never_reach_the_current_primary(self):
        cells_row = row("ada.work@example.com", Primary_Verified="FALSE", Primary_Subscribed="FALSE")

        (outcome,) = self.apply([cells_row], {2: ("update", [])})

        primary = ContactEmail.objects.get(email_address="ada@example.com")
        self.work.refresh_from_db()
        self.assertEqual((primary.verified, primary.subscribe), (True, True))
        self.assertEqual((self.work.verified, self.work.subscribe), (True, False))
        self.assertIn(
            "Primary Verified is FALSE, but ada.work@example.com is verified; left verified (un-verifying needs its "
            "tick)",
            outcome.notes,
        )

    def test_make_primary_promotes_the_address_and_demotes_the_old_ones(self):
        old = self.email(self.ada, "ada.old@example.com", "other", verified=True)

        (outcome,) = self.apply([row("ada.old@example.com")], {2: ("update_make_primary", [])})

        self.assertEqual(outcome.outcome, "updated")
        self.assertEqual(
            roles(self.ada),
            {"ada.old@example.com": "primary", "ada@example.com": "secondary", "ada.work@example.com": "other"},
        )
        self.assertIn(
            "Makes ada.old@example.com the primary email; the previous primary ada@example.com becomes secondary; the "
            'previous secondary ada.work@example.com becomes "other"; nothing is deleted',
            outcome.changes,
        )
        self.assertEqual(outcome.listed["primary_changes"], ["ada.old@example.com made primary"])
        old.refresh_from_db()
        self.assertTrue(old.verified)

    def test_make_primary_for_a_member_without_a_primary(self):
        lee = self.member("Lee", "Legacy")
        self.email(lee, "lee.old@example.com", verified=True)

        (outcome,) = self.apply(
            [row("lee.old@example.com", First_Name="Lee", Last_Name="Legacy")], {2: ("update_make_primary", [])}
        )

        self.assertEqual(roles(lee), {"lee.old@example.com": "primary"})
        self.assertIn("Makes lee.old@example.com the primary email; nothing is deleted", outcome.changes)

    def test_make_primary_of_the_secondary_swaps_the_two(self):
        (outcome,) = self.apply([row("ada.work@example.com")], {2: ("update_make_primary", [])})

        self.assertEqual(roles(self.ada), {"ada.work@example.com": "primary", "ada@example.com": "secondary"})
        self.assertIn(
            "Makes ada.work@example.com the primary email; the previous primary ada@example.com becomes secondary; "
            "nothing is deleted",
            outcome.changes,
        )

    def test_skipped_by_default(self):
        (outcome,) = self.apply([row("ada.work@example.com", Organization="Spirit")])

        self.assertEqual(outcome.outcome, "skipped")
        self.ada.refresh_from_db()
        self.assertIsNone(self.ada.organization)
