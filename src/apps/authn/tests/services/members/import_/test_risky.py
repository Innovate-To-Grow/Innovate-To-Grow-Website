"""Risky changes (R1–R8): opt-in ticks, off by default, some of which can't be ticked at all.

Without a tick an import never deletes a contact, re-subscribes or un-verifies one, or changes Active or Staff; with
the tick the change is made. An item that may not be ticked says why: the address the row matched on, the member's
only verified sign-in contact, or an account only an I2G Master may change. The safe direction (TRUE verifies, FALSE
unsubscribes) needs no tick, and contacts added to an existing member start unverified.
"""

from django.core import mail

from apps.authn.models import ContactEmail, ContactPhone
from apps.authn.services.members.import_.review.plan import PENDING_NOTE
from apps.authn.services.members.import_.review.risky import MASTER_ONLY, MATCHED, PENDING, PRIVILEGED
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


class NamedSecondaryTests(RiskyTestCase):
    """R2: the sheet names a secondary, and the member has others."""

    def setUp(self):
        super().setUp()
        self.old = self.email(self.ada, "ada.old@example.com")

    def test_a_new_secondary_offers_to_remove_the_others(self):
        analysis = self.analyse_one(row("ada@example.com", Secondary_Email="ada.new@example.com"))

        items = self.items(analysis)
        self.assertEqual(list(items), [f"R2:{self.old.pk}"])
        self.assertItem(
            items[f"R2:{self.old.pk}"], "Remove secondary ada.old@example.com (the sheet names ada.new@example.com)"
        )
        self.assertEqual(analysis.status, "ready_update")

    def test_unticked_the_new_secondary_is_added_unverified_and_the_old_one_becomes_other(self):
        outcome = self.ticked(row("ada@example.com", Secondary_Email="ada.new@example.com", Secondary_Verified="TRUE"))

        self.assertEqual(
            roles(self.ada),
            {"ada@example.com": "primary", "ada.new@example.com": "secondary", "ada.old@example.com": "other"},
        )
        self.assertFalse(ContactEmail.objects.get(email_address="ada.new@example.com").verified)
        self.assertIn(
            "Adds ada.new@example.com as the secondary email (unverified, subscribed); the previous secondary "
            'ada.old@example.com becomes "other"',
            outcome.changes,
        )
        self.assertIn(
            "ada.new@example.com is added unverified (contacts added to an existing member start unverified; the "
            "member verifies them on /account)",
            outcome.notes,
        )

    def test_ticked_the_old_secondary_is_removed(self):
        outcome = self.ticked(row("ada@example.com", Secondary_Email="ada.new@example.com"), f"R2:{self.old.pk}")

        self.assertEqual(roles(self.ada), {"ada@example.com": "primary", "ada.new@example.com": "secondary"})
        self.assertEqual(outcome.listed["emails_deleted"], ["secondary ada.old@example.com"])

    def test_naming_one_of_two_secondaries_offers_the_other(self):
        two = self.email(self.ada, "ada.two@example.com")
        cells_row = row("ada@example.com", Secondary_Email="ada.old@example.com")

        self.assertEqual(list(self.items(self.analyse_one(cells_row))), [f"R2:{two.pk}"])
        self.ticked(cells_row, f"R2:{two.pk}")

        self.assertEqual(roles(self.ada), {"ada@example.com": "primary", "ada.old@example.com": "secondary"})

    def test_an_address_of_another_member_is_never_moved(self):
        grace = self.member("Grace", "Hopper", "grace@example.com")
        cells_row = row("ada@example.com", Secondary_Email="grace@example.com", Secondary_Verified="FALSE")

        analysis = self.analyse_one(cells_row)
        outcome = self.ticked(cells_row)

        self.assertEqual(analysis.risky, {})
        self.assertEqual(ContactEmail.objects.get(email_address="grace@example.com").member, grace)
        self.assertTrue(ContactEmail.objects.get(email_address="grace@example.com").verified)
        self.assertEqual(roles(self.ada), {"ada@example.com": "primary", "ada.old@example.com": "secondary"})
        self.assertIn(
            f"Secondary Email grace@example.com belongs to Grace Hopper (member {grace.pk}); not added (an import "
            "never moves a contact from one member to another)",
            outcome.notes,
        )

    def test_an_unlinked_secondary_is_attached_unverified(self):
        loose = ContactEmail.objects.create(
            member=None, email_address="loose@example.com", verified=True, subscribe=False
        )
        cells_row = row("ada@example.com", Secondary_Email="loose@example.com", Secondary_Verified="TRUE")

        self.assertEqual(list(self.items(self.analyse_one(cells_row))), [f"R2:{self.old.pk}"])
        self.ticked(cells_row)

        loose.refresh_from_db()
        self.assertEqual(
            (loose.member, loose.email_type, loose.verified, loose.subscribe), (self.ada, "secondary", False, False)
        )
        self.assertEqual(roles(self.ada)["ada.old@example.com"], "other")


class BlankPhoneTests(RiskyTestCase):
    """R3: the Phone Number column is in the sheet, and the row's cell is blank."""

    def setUp(self):
        super().setUp()
        self.mobile = self.phone(self.ada, "2095550101", verified=True)
        self.desk = self.phone(self.ada, "2095550102")

    def test_one_item_per_phone(self):
        items = self.items(self.analyse_one(row("ada@example.com")))

        self.assertEqual(set(items), {f"R3:{self.mobile.pk}", f"R3:{self.desk.pk}"})
        self.assertItem(items[f"R3:{self.mobile.pk}"], "Remove phone +12095550101 (the Phone Number cell is blank)")

    def test_no_item_without_the_column(self):
        analysis = self.analyse_one(
            ["ada@example.com", "Ada", "Lovelace"], ["Primary Email", "First Name", "Last Name"]
        )

        self.assertEqual(analysis.risky, {})

    def test_unticked_every_phone_is_kept(self):
        outcome = self.ticked(row("ada@example.com"))

        self.assertEqual(self.ada.contact_phones.count(), 2)
        self.assertTrue(any(note.startswith("Phone Number is blank; kept +1209555010") for note in outcome.notes))

    def test_ticked_only_that_phone_is_removed(self):
        outcome = self.ticked(row("ada@example.com"), f"R3:{self.desk.pk}")

        self.assertEqual(list(self.ada.contact_phones.values_list("phone_number", flat=True)), ["2095550101"])
        self.assertEqual(outcome.listed["phones_deleted"], ["phone +12095550102"])


class NewNumberTests(RiskyTestCase):
    """R4: the sheet names a number the database doesn't have."""

    def setUp(self):
        super().setUp()
        self.mobile = self.phone(self.ada, "2095550101", verified=True, subscribe=True)
        self.new_number = row(
            "ada@example.com", Phone_Number="209-555-0199", Phone_Verified="TRUE", Phone_Subscribed="TRUE"
        )

    def test_a_new_number_offers_to_remove_the_old_ones(self):
        items = self.items(self.analyse_one(self.new_number))

        self.assertEqual(list(items), [f"R4:{self.mobile.pk}"])
        self.assertItem(items[f"R4:{self.mobile.pk}"], "Remove old phone +12095550101 (the sheet names +12095550199)")

    def test_unticked_the_number_is_added_unverified_next_to_the_old_one(self):
        outcome = self.ticked(self.new_number)

        new = ContactPhone.objects.get(phone_number="2095550199")
        self.assertEqual((new.member, new.verified, new.subscribe), (self.ada, False, True))
        self.mobile.refresh_from_db()
        self.assertTrue(self.mobile.verified)
        self.assertIn(
            "Adds phone +12095550199 (unverified, subscribed); keeps +12095550101 (an import never replaces a number "
            "in place)",
            outcome.changes,
        )
        self.assertIn(
            "+12095550199 is added unverified (contacts added to an existing member start unverified; the member "
            "verifies them on /account)",
            outcome.notes,
        )

    def test_ticked_the_old_number_is_removed_and_the_new_one_never_inherits_verified(self):
        self.ticked(self.new_number, f"R4:{self.mobile.pk}")

        self.assertEqual(list(self.ada.contact_phones.values_list("phone_number", "verified")), [("2095550199", False)])

    def test_a_stored_number_offers_no_removal(self):
        grace = self.member("Grace", "Hopper", "grace@example.com")
        self.phone(grace, "2095550188")

        own = self.analyse_one(row("ada@example.com", Phone_Number="2095550101"))
        taken = row("ada@example.com", Phone_Number="2095550188")
        outcome = self.ticked(taken)

        self.assertEqual((own.risky, self.analyse_one(taken).risky), ({}, {}))
        self.assertEqual(ContactPhone.objects.get(phone_number="2095550188").member, grace)
        self.assertIn(
            f"Phone Number +12095550188 belongs to Grace Hopper (member {grace.pk}); not added (an import never "
            "moves a contact from one member to another)",
            outcome.notes,
        )


class ResubscribeTests(RiskyTestCase):
    """R5: a Subscribed cell is TRUE for a contact of the member that is unsubscribed."""

    def test_the_primary_address(self):
        ContactEmail.objects.filter(pk=self.primary.pk).update(subscribe=False)
        cells_row = row("ada@example.com", Primary_Subscribed="TRUE")

        items = self.items(self.analyse_one(cells_row))
        unticked = self.ticked(cells_row)
        self.primary.refresh_from_db()
        self.assertFalse(self.primary.subscribe)
        ticked = self.ticked(cells_row, f"R5:{self.primary.pk}")

        self.assertItem(items[f"R5:{self.primary.pk}"], "Re-subscribe ada@example.com")
        self.assertIn(
            "Primary Subscribed is TRUE, but ada@example.com is unsubscribed; left unsubscribed (re-subscribing needs "
            "the person's consent and its tick)",
            unticked.notes,
        )
        self.primary.refresh_from_db()
        self.assertTrue(self.primary.subscribe)
        self.assertEqual(ticked.listed["resubscribed"], ["ada@example.com"])

    def test_the_secondary_address_and_the_phone(self):
        work = self.email(self.ada, "ada.work@example.com", subscribe=False)
        mobile = self.phone(self.ada, "2095550101", subscribe=False)
        cells = {"Secondary_Subscribed": "TRUE", "Phone_Number": "2095550101", "Phone_Subscribed": "TRUE"}
        cells_row = row("ada@example.com", Secondary_Email="ada.work@example.com", **cells)

        items = self.items(self.analyse_one(cells_row))
        self.ticked(cells_row, f"R5:{work.pk}", f"R5:{mobile.pk}")

        self.assertItem(items[f"R5:{work.pk}"], "Re-subscribe ada.work@example.com")
        self.assertItem(items[f"R5:{mobile.pk}"], "Re-subscribe +12095550101")
        work.refresh_from_db()
        mobile.refresh_from_db()
        self.assertEqual((work.subscribe, mobile.subscribe), (True, True))


class UnverifyTests(RiskyTestCase):
    """R6: a Verified cell is FALSE for a contact of the member that is verified."""

    def setUp(self):
        super().setUp()
        self.mobile = self.phone(self.ada, "2095550101", verified=True)
        self.cells_row = row("ada@example.com", Primary_Verified="FALSE")

    def test_off_and_on(self):
        items = self.items(self.analyse_one(self.cells_row))
        unticked = self.ticked(self.cells_row)
        self.primary.refresh_from_db()
        self.assertTrue(self.primary.verified)
        ticked = self.ticked(self.cells_row, f"R6:{self.primary.pk}")

        self.assertItem(items[f"R6:{self.primary.pk}"], "Mark ada@example.com unverified")
        self.assertIn(
            "Primary Verified is FALSE, but ada@example.com is verified; left verified (un-verifying needs its tick)",
            unticked.notes,
        )
        self.primary.refresh_from_db()
        self.assertFalse(self.primary.verified)
        self.assertEqual(ticked.listed["unverified"], ["ada@example.com"])

    def test_the_phone(self):
        items = self.items(self.analyse_one(row("ada@example.com", Phone_Number="2095550101", Phone_Verified="FALSE")))

        self.assertItem(items[f"R6:{self.mobile.pk}"], "Mark +12095550101 unverified")

    def test_the_only_verified_contact_cannot_be_unverified(self):
        self.mobile.delete()

        items = self.items(self.analyse_one(self.cells_row))

        self.assertItem(items[f"R6:{self.primary.pk}"], "Mark ada@example.com unverified", LAST_ADA)


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
