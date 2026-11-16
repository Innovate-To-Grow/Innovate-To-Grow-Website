from apps.authn.models import ContactEmail
from apps.authn.tests.services.members.import_.helpers import row
from apps.authn.tests.services.members.import_.review.test_risky import RiskyTestCase, roles


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
