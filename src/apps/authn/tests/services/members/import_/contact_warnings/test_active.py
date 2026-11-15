from django.core import mail

from apps.authn.models import ContactEmail
from apps.authn.services.members.import_.review.analysis.risky import MASTER_ONLY, PENDING, PRIVILEGED
from apps.authn.services.members.import_.review.plan import PENDING_NOTE
from apps.authn.tests.services.members.import_.helpers import row
from apps.authn.tests.services.members.import_.review.test_risky import RiskyTestCase, roles


class ActiveTests(RiskyTestCase):
    """R7: the Active cell differs from the member's status."""

    def test_deactivate_off_and_on(self):
        cells_row = row("ada@example.com", Active="No")

        analysis = self.analyse_one(cells_row)
        unticked = self.ticked(cells_row)
        self.ada.refresh_from_db()
        self.assertTrue(self.ada.is_active)
        ticked = self.ticked(cells_row, f"R7:{self.ada.pk}")

        self.assertEqual(analysis.status, "no_change")
        self.assertItem(self.items(analysis)[f"R7:{self.ada.pk}"], "Deactivate the member")
        self.assertIn(
            "Active is FALSE, but the member is active; left active (activating or deactivating a member needs its "
            "tick)",
            unticked.notes,
        )
        self.ada.refresh_from_db()
        self.assertFalse(self.ada.is_active)
        self.assertEqual(ticked.listed["active_changes"], [f"Ada Lovelace (member {self.ada.pk}): deactivated"])

    def test_an_unfinished_sign_up_is_never_activated(self):
        """Only the person finishes their sign-up; a squatter's account must not be activated by an import."""
        pat = self.member("Pat", "Pending", "pat@example.com", is_active=False, registration_pending=True)
        cells_row = row("pat@example.com", First_Name="Pat", Last_Name="Pending", Active="Yes")

        items = self.items(self.analyse_one(cells_row), pat)
        outcome = self.ticked(cells_row, f"R7:{pat.pk}")  # even a forged tick that skipped the review's checks

        self.assertItem(items[f"R7:{pat.pk}"], "Reactivate the member", PENDING)
        self.assertEqual(outcome.outcome, "no_change")
        self.assertIn(PENDING_NOTE, outcome.notes)
        pat.refresh_from_db()
        self.assertEqual((pat.is_active, pat.registration_pending), (False, True))

    def test_a_privileged_member_needs_an_i2g_master(self):
        sam = self.member("Sam", "Staff", "sam@example.com", is_staff=True)
        cells_row = row("sam@example.com", First_Name="Sam", Last_Name="Staff", Active="No")

        not_master = self.items(self.analyse_one(cells_row), sam)
        master = self.items(self.analyse_one(cells_row, is_master=True), sam)

        self.assertItem(not_master[f"R7:{sam.pk}"], "Deactivate the member", PRIVILEGED)
        self.assertTrue(master[f"R7:{sam.pk}"]["enabled"])

    def test_the_same_status_offers_nothing(self):
        self.assertEqual(self.analyse_one(row("ada@example.com", Active="Yes")).risky, {})


class StaffTests(RiskyTestCase):
    """R8: the Staff cell differs; only an I2G Master may tick it."""

    def test_only_an_i2g_master_may_tick_it(self):
        cells_row = row("ada@example.com", Staff="Yes")

        not_master = self.items(self.analyse_one(cells_row))
        master = self.items(self.analyse_one(cells_row, is_master=True))

        self.assertItem(not_master[f"R8:{self.ada.pk}"], "Grant staff status", MASTER_ONLY)
        self.assertItem(master[f"R8:{self.ada.pk}"], "Grant staff status")

    def test_off_and_on(self):
        cells_row = row("ada@example.com", Staff="Yes")

        unticked = self.ticked(cells_row, is_master=True)
        self.ada.refresh_from_db()
        self.assertFalse(self.ada.is_staff)
        ticked = self.ticked(cells_row, f"R8:{self.ada.pk}", is_master=True)

        self.assertIn(
            "Staff column ignored (only an I2G Master may change staff status, with its tick)", unticked.notes
        )
        self.ada.refresh_from_db()
        self.assertTrue(self.ada.is_staff)
        self.assertEqual(ticked.listed["staff_changes"], [f"Ada Lovelace (member {self.ada.pk}): staff granted"])

    def test_removing_staff_status(self):
        sam = self.member("Sam", "Staff", "sam@example.com", is_staff=True)
        cells_row = row("sam@example.com", First_Name="Sam", Last_Name="Staff", Staff="No")

        items = self.items(self.analyse_one(cells_row, is_master=True), sam)
        self.ticked(cells_row, f"R8:{sam.pk}", is_master=True)

        self.assertItem(items[f"R8:{sam.pk}"], "Remove staff status")
        sam.refresh_from_db()
        self.assertFalse(sam.is_staff)


class NothingWithoutTicksTests(RiskyTestCase):
    """One row that asks for every risky change: nothing happens without the ticks, everything with them."""

    def setUp(self):
        super().setUp()
        ContactEmail.objects.filter(pk=self.primary.pk).update(subscribe=False)
        self.work = self.email(self.ada, "ada.work@example.com", verified=True)
        self.old = self.email(self.ada, "ada.old@example.com", "other", verified=True)
        self.mobile = self.phone(self.ada, "2095550101", verified=True)
        cells = {"Primary_Verified": "FALSE", "Primary_Subscribed": "TRUE", "Active": "No", "Staff": "Yes"}
        self.cells_row = row("ada@example.com", Phone_Number="2095550199", Organization="Engines", **cells)
        self.ticks = [
            f"R1:{self.work.pk}",
            f"R4:{self.mobile.pk}",
            f"R5:{self.primary.pk}",
            f"R6:{self.primary.pk}",
            f"R7:{self.ada.pk}",
            f"R8:{self.ada.pk}",
        ]

    def test_every_item_is_offered(self):
        items = self.items(self.analyse_one(self.cells_row, is_master=True))

        self.assertEqual(set(items), set(self.ticks))
        self.assertTrue(all(item["enabled"] for item in items.values()))

    def test_without_ticks_only_the_safe_changes_are_made(self):
        (outcome,) = self.apply([self.cells_row], is_master=True)

        self.assertEqual(outcome.outcome, "updated")
        self.ada.refresh_from_db()
        self.primary.refresh_from_db()
        self.assertEqual((self.ada.organization, self.ada.is_active, self.ada.is_staff), ("Engines", True, False))
        self.assertEqual((self.primary.verified, self.primary.subscribe), (True, False))
        self.assertEqual(self.ada.contact_emails.count(), 3)
        self.assertEqual(
            sorted(self.ada.contact_phones.values_list("phone_number", "verified")),
            [("2095550101", True), ("2095550199", False)],
        )
        self.assertEqual(mail.outbox, [])

    def test_with_every_tick_every_change_is_made(self):
        outcome = self.ticked(self.cells_row, *self.ticks, is_master=True)

        self.ada.refresh_from_db()
        self.primary.refresh_from_db()
        self.assertEqual((self.ada.is_active, self.ada.is_staff), (False, True))
        self.assertEqual((self.primary.verified, self.primary.subscribe), (False, True))
        self.assertEqual(roles(self.ada), {"ada@example.com": "primary", "ada.old@example.com": "other"})
        self.assertEqual(list(self.ada.contact_phones.values_list("phone_number", "verified")), [("2095550199", False)])
        self.assertEqual(
            {kind: len(items) for kind, items in outcome.listed.items()},
            {
                "unverified": 1,
                "resubscribed": 1,
                "emails_deleted": 1,
                "phones_deleted": 1,
                "active_changes": 1,
                "staff_changes": 1,
            },
        )
        self.assertEqual(mail.outbox, [])
