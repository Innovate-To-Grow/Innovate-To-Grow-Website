from apps.authn.models import ContactEmail, ContactPhone
from apps.authn.tests.services.members.import_.helpers import ImportTestCase, row
from apps.authn.tests.services.members.import_.reading.test_validation import V8_LAB, codes


class _SecondaryEmailWarningCase(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.secondary = self.email(self.ada, "ada.work@example.com")


class SecondaryEmailWarningTests(_SecondaryEmailWarningCase):
    def test_v2_an_invalid_new_secondary_is_ignored(self):
        analysis = self.analyse_one(row("ada@example.com", Secondary_Email="not-an-email"))

        warning = {"code": "V2", "text": "Secondary Email 'not-an-email' is not a valid email address; ignored"}
        self.assertEqual(analysis.warnings, [warning])
        self.assertEqual(analysis.drops, {"secondary_email": warning})
        # A cell set aside reads as a missing column: it offers no removal of the stored secondary.
        self.assertEqual((analysis.status, analysis.risky), ("no_change", {}))

    def test_v2_does_not_apply_to_an_address_that_is_stored(self):
        grace = self.member("Grace", "Hopper", "grace@example.com")
        self.email(grace, "odd@@example.com")

        analysis = self.analyse_one(row("ada@example.com", Secondary_Email="odd@@example.com"))

        self.assertEqual(analysis.warnings, [])

    def test_v7_the_secondary_is_the_primary(self):
        analysis = self.analyse_one(row("ada@example.com", Secondary_Email="ADA@example.com"))

        self.assertEqual(
            analysis.warnings, [{"code": "V7", "text": "Secondary Email is the same as the Primary Email; ignored"}]
        )
        self.assertEqual((analysis.status, analysis.risky), ("no_change", {}))

    def test_v8_the_secondary_is_another_rows_primary(self):
        rows = [
            row("one@example.com", Secondary_Email="two@example.com"),
            row("two@example.com", Secondary_Email="one@example.com"),
        ]

        first, second = self.analyse(rows)

        self.assertEqual(
            first.warnings,
            [
                {
                    "code": "V8",
                    "text": "Secondary Email two@example.com is the Primary Email of row 3; that row wins, and this "
                    "cell is ignored",
                }
            ],
        )
        self.assertEqual(codes(second), ["V8"])
        self.assertIn("is the Primary Email of row 2", second.warnings[0]["text"])

    def test_v8_the_same_new_secondary_in_two_rows(self):
        rows = [
            row("one@example.com", Secondary_Email="shared.new@example.com"),
            row("two@example.com", Secondary_Email="Shared.New@example.com"),
        ]

        first, second = self.analyse(rows)

        self.assertEqual(first.warnings, [])
        self.assertEqual(
            second.warnings,
            [
                {
                    "code": "V8",
                    "text": "Secondary Email Shared.New@example.com is also in row 2; only that row can add it; if that row is skipped, no row adds it",
                }
            ],
        )

    def test_a_stored_secondary_in_two_rows_is_not_v8(self):
        rows = [
            row("one@example.com", Secondary_Email="ada.work@example.com"),
            row("two@example.com", Secondary_Email="ada.work@example.com"),
        ]

        analyses = self.analyse(rows)

        self.assertEqual([a.warnings for a in analyses], [[], []])

    def test_v8_the_same_unlinked_secondary_in_two_rows(self):
        ContactEmail.objects.create(member=None, email_address="lab@example.com", email_type="primary")
        rows = [
            row("one@example.com", Secondary_Email="lab@example.com"),
            row("two@example.com", Secondary_Email="LAB@example.com"),
        ]

        first, second = self.analyse(rows)

        self.assertEqual(first.warnings, [])
        self.assertEqual(
            second.warnings,
            [
                {
                    "code": "V8",
                    "text": "Secondary Email LAB@example.com is also in row 2; only that row can add it; if that row is skipped, no row adds it",
                }
            ],
        )

    def test_only_the_first_row_attaches_a_shared_unlinked_secondary(self):
        # Both rows used to plan the claim, so the second claim failed the whole apply ("taken … after the review").
        lab = ContactEmail.objects.create(member=None, email_address="lab@example.com", email_type="primary")
        rows = [
            row("ada@example.com", Secondary_Email="lab@example.com"),
            row("two@example.com", First_Name="Tom", Secondary_Email="lab@example.com"),
        ]

        first, second = self.apply(rows)

        self.assertEqual((first.outcome, second.outcome), ("updated", "created"))
        lab.refresh_from_db()
        self.assertEqual((lab.member, lab.email_type, lab.verified), (self.ada, "secondary", False))
        self.assertEqual(
            list(second.member.contact_emails.values_list("email_address", flat=True)), ["two@example.com"]
        )

    def test_a_row_that_cannot_be_imported_takes_no_cell(self):
        # The first row naming them has no Primary Email, so it is never imported: the next row adds them.
        lab = ContactEmail.objects.create(member=None, email_address="lab@example.com", email_type="primary")
        rows = [
            row(None, Secondary_Email="lab@example.com", Phone_Number="2095550123"),
            row("ada@example.com", Secondary_Email="lab@example.com", Phone_Number="2095550123"),
        ]

        invalid, ada = self.analyse(rows)

        self.assertEqual((invalid.status, ada.status, ada.warnings), ("invalid", "ready_update", []))
        outcomes = self.apply(rows)
        self.assertEqual([outcome.outcome for outcome in outcomes], ["not_imported", "updated"])
        lab.refresh_from_db()
        self.assertEqual((lab.member, lab.email_type), (self.ada, "secondary"))
        self.assertEqual(ContactPhone.objects.get(phone_number="2095550123").member, self.ada)

    def test_the_primary_of_a_row_that_cannot_be_imported_does_not_win(self):
        # A new member without a last name is never created, so its Primary Email sets no other row's cell aside.
        rows = [row("new@example.com", Last_Name=None), row("ada@example.com", Secondary_Email="new@example.com")]

        invalid, ada = self.analyse(rows)

        self.assertEqual((invalid.status, invalid.facts["invalid"]), ("invalid", "Missing last name"))
        self.assertEqual(ada.warnings, [])
        self.apply(rows)
        self.assertEqual(ContactEmail.objects.get(email_address="new@example.com").member, self.ada)

    def test_a_shared_unlinked_secondary_stays_unlinked_when_its_first_row_is_skipped(self):
        # The cell goes to the first row in sheet order, before anyone chooses. Row 2 needs a decision (C6) and stays
        # on Skip, so no row attaches the address, as row 3's warning says.
        lab = ContactEmail.objects.create(member=None, email_address="lab@example.com", email_type="primary")
        rows = [
            row("ada@example.com", First_Name="Augusta", Last_Name="King", Secondary_Email="lab@example.com"),
            row("tom@example.com", First_Name="Tom", Last_Name="Thumb", Secondary_Email="lab@example.com"),
        ]

        skipped, created = self.analyse(rows)

        self.assertEqual((skipped.conflict, skipped.default), ("name_differs", "skip"))
        self.assertEqual(created.warnings, [{"code": "V8", "text": V8_LAB}])
        outcomes = self.apply(rows)
        self.assertEqual([outcome.outcome for outcome in outcomes], ["skipped", "created"])
        lab.refresh_from_db()
        self.assertIsNone(lab.member)
        self.assertEqual(
            list(outcomes[1].member.contact_emails.values_list("email_address", flat=True)), ["tom@example.com"]
        )
