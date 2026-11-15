"""Risky changes (R1–R9): opt-in ticks, off by default, some of which can't be ticked at all.

Without a tick an import never deletes a contact, re-subscribes or un-verifies one, or changes Active or Staff; with
the tick the change is made. An item that may not be ticked says why: the address the row matched on, the member's
only verified sign-in contact, or an account only an I2G Master may change. The safe direction (TRUE verifies, FALSE
unsubscribes) needs no tick, and contacts added to an existing member start unverified.
"""

from apps.authn.models import ContactEmail
from apps.authn.services.members.import_.review.analysis.risky import MATCHED, PRIVILEGED
from apps.authn.tests.services.members.import_.helpers import ImportTestCase, row

LAST_ADA = "It is the only verified sign-in contact of Ada Lovelace"


def roles(member) -> dict:
    return dict(member.contact_emails.values_list("email_address", "email_type"))


class RiskyTestCase(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.primary = self.ada.contact_emails.get()

    def items(self, analysis, member=None) -> dict:
        return {item["id"]: item for item in analysis.risky.get(str((member or self.ada).pk), [])}

    def ticked(self, cells_row, *ticks, choice="update", **context):
        """Apply one row with ``choice`` and ``ticks``; return its outcome."""
        (outcome,) = self.apply([cells_row], {2: (choice, list(ticks))}, **context)
        return outcome

    def assertItem(self, item, label, reason=""):
        self.assertEqual((item["label"], item["enabled"], item["reason"]), (label, not reason, reason))


class BlankSecondaryTests(RiskyTestCase):
    """R1: the Secondary Email column is in the sheet, and the row's cell is blank."""

    def setUp(self):
        super().setUp()
        self.work = self.email(self.ada, "ada.work@example.com")
        self.home = self.email(self.ada, "ada.home@example.com")
        self.email(self.ada, "ada.old@example.com", "other")

    def test_one_item_per_secondary(self):
        analysis = self.analyse_one(row("ada@example.com"))

        items = self.items(analysis)
        self.assertEqual(set(items), {f"R1:{self.work.pk}", f"R1:{self.home.pk}"})
        self.assertItem(
            items[f"R1:{self.work.pk}"], "Remove secondary ada.work@example.com (the Secondary Email cell is blank)"
        )
        self.assertEqual(items[f"R1:{self.home.pk}"]["code"], "R1")
        self.assertEqual((analysis.status, analysis.default), ("no_change", "update"))

    def test_no_item_without_the_column(self):
        analysis = self.analyse_one(
            ["ada@example.com", "Ada", "Lovelace"], ["Primary Email", "First Name", "Last Name"]
        )

        self.assertEqual(analysis.risky, {})

    def test_unticked_every_secondary_is_kept(self):
        outcome = self.ticked(row("ada@example.com"))

        self.assertEqual(outcome.outcome, "no_change")
        self.assertEqual(self.ada.contact_emails.count(), 4)
        (note,) = [note for note in outcome.notes if note.startswith("Secondary Email is blank; kept ")]
        self.assertIn("ada.work@example.com", note)
        self.assertIn("ada.home@example.com", note)
        self.assertTrue(note.endswith("(nothing is removed unless its removal is ticked in the review)"))

    def test_ticked_only_that_secondary_is_removed(self):
        outcome = self.ticked(row("ada@example.com"), f"R1:{self.work.pk}")

        self.assertEqual(outcome.outcome, "updated")
        self.assertFalse(ContactEmail.objects.filter(pk=self.work.pk).exists())
        self.assertTrue(ContactEmail.objects.filter(pk=self.home.pk).exists())
        self.assertEqual(outcome.listed["emails_deleted"], ["secondary ada.work@example.com"])

    def test_the_address_the_row_matched_on_cannot_be_removed(self):
        analysis = self.analyse_one(row("ada.work@example.com"))

        items = self.items(analysis)
        self.assertEqual(analysis.conflict, "address_not_primary")
        self.assertItem(
            items[f"R1:{self.work.pk}"],
            "Remove secondary ada.work@example.com (the Secondary Email cell is blank)",
            MATCHED,
        )
        self.assertTrue(items[f"R1:{self.home.pk}"]["enabled"])

    def test_the_only_verified_contact_cannot_be_removed(self):
        ContactEmail.objects.filter(pk=self.primary.pk).update(verified=False)
        ContactEmail.objects.filter(pk=self.work.pk).update(verified=True)

        items = self.items(self.analyse_one(row("ada@example.com")))

        self.assertEqual(items[f"R1:{self.work.pk}"]["reason"], LAST_ADA)
        self.assertTrue(items[f"R1:{self.home.pk}"]["enabled"])

    def test_a_privileged_member_needs_an_i2g_master(self):
        sam = self.member("Sam", "Staff", "sam@example.com", is_staff=True)
        extra = self.email(sam, "sam.work@example.com")
        cells_row = row("sam@example.com", First_Name="Sam", Last_Name="Staff")

        not_master = self.items(self.analyse_one(cells_row), sam)
        master = self.items(self.analyse_one(cells_row, is_master=True), sam)

        self.assertEqual(not_master[f"R1:{extra.pk}"]["reason"], PRIVILEGED)
        self.assertTrue(master[f"R1:{extra.pk}"]["enabled"])
