from apps.authn.models import ContactEmail, ContactPhone
from apps.authn.tests.services.members.import_.helpers import row
from apps.authn.tests.services.members.import_.review.test_risky import LAST_ADA, RiskyTestCase


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
        # The sheet's Phone Verified TRUE is ignored, not reported row by row.
        self.assertFalse(any("Phone Verified" in note or "added unverified" in note for note in outcome.notes))

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

    def test_an_unsubscribed_address_with_no_member_is_never_re_subscribed(self):
        """A ready row attaches an unlinked Secondary Email; its Subscribed TRUE can't undo the record's opt-out."""
        loose = ContactEmail.objects.create(member=None, email_address="loose@example.com", subscribe=False)
        cells_row = row("ada@example.com", Secondary_Email="loose@example.com", Secondary_Subscribed="TRUE")

        analysis = self.analyse_one(cells_row)
        outcome = self.ticked(cells_row)

        self.assertEqual(analysis.status, "ready_update")
        self.assertFalse(any(item["code"] == "R5" for item in analysis.risky.get(str(self.ada.pk), [])))
        loose.refresh_from_db()
        self.assertEqual((loose.member, loose.email_type, loose.subscribe), (self.ada, "secondary", False))
        self.assertIn(
            "Secondary Subscribed is TRUE, but loose@example.com is unsubscribed; left unsubscribed (an import never "
            "re-subscribes an address; with the person's consent, re-subscribe it under Contact Emails)",
            outcome.notes,
        )

    def test_a_new_member_never_re_subscribes_an_address_with_no_member(self):
        loose = ContactEmail.objects.create(member=None, email_address="loose@example.com", subscribe=False)
        cells_row = row(
            "grace@example.com",
            First_Name="Grace",
            Last_Name="Hopper",
            Secondary_Email="loose@example.com",
            Secondary_Subscribed="TRUE",
        )

        (outcome,) = self.apply([cells_row])

        self.assertEqual(outcome.outcome, "created")
        loose.refresh_from_db()
        self.assertEqual((loose.member, loose.email_type, loose.subscribe), (outcome.member, "secondary", False))
        self.assertIn(
            "Attaches loose@example.com (a contact email with no member) as the secondary email (unverified, not "
            "subscribed)",
            outcome.changes,
        )


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

    def test_a_phone_number_is_never_offered(self):
        """The Phone Verified column is ignored: a stored number keeps its status, so there is nothing to tick."""
        analysis = self.analyse_one(row("ada@example.com", Phone_Number="2095550101", Phone_Verified="FALSE"))

        self.assertEqual(self.items(analysis), {})
        self.assertEqual(analysis.status, "no_change")

    def test_the_only_verified_contact_cannot_be_unverified(self):
        self.mobile.delete()

        items = self.items(self.analyse_one(self.cells_row))

        self.assertItem(items[f"R6:{self.primary.pk}"], "Mark ada@example.com unverified", LAST_ADA)
