"""Rows that cannot be imported, and the warnings (V2, V4–V8) that set a cell aside while the row is still imported."""

from apps.authn.models import ContactEmail, ContactPhone, Member
from apps.authn.tests.services.members.import_.helpers import HEADERS, ImportTestCase, row


def codes(analysis) -> list[str]:
    return [warning["code"] for warning in analysis.warnings]


V8_LAB = (
    "Secondary Email lab@example.com is also in row 2; only that row can add it; if that row is skipped, no row adds it"
)


class InvalidRowTests(ImportTestCase):
    def test_a_row_without_a_primary_email(self):
        analysis = self.analyse_one(row(None, Organization="Engines"))

        self.assertEqual((analysis.status, analysis.conflict), ("invalid", ""))
        self.assertEqual(analysis.facts["invalid"], "Missing primary email")
        self.assertEqual((analysis.options, analysis.default, analysis.risky), ([], "skip", {}))

    def test_a_new_primary_address_must_be_valid(self):
        too_long = f"{'a' * 250}@example.com"
        cases = {
            "not-an-email": "Primary Email 'not-an-email' is not a valid email address",
            "two@@example.com": "Primary Email 'two@@example.com' is not a valid email address",
            too_long: f"Primary Email {too_long!r} is not a valid email address",
        }
        for address, reason in cases.items():
            with self.subTest(address=address[:20]):
                analysis = self.analyse_one(row(address))
                self.assertEqual((analysis.status, analysis.facts["invalid"]), ("invalid", reason))

    def test_a_stored_address_is_not_validated_again(self):
        self.member("Lee", "Gacy", "legacy@@example.com")

        analysis = self.analyse_one(row("legacy@@example.com", First_Name="Lee", Last_Name="Gacy", Title="Archivist"))

        self.assertEqual((analysis.status, analysis.conflict), ("ready_update", ""))

    def test_a_new_member_needs_a_first_and_a_last_name(self):
        cases = [
            ({"First_Name": None}, "Missing first name"),
            ({"Last_Name": None}, "Missing last name"),
            ({"First_Name": "  ", "Last_Name": None}, "Missing first name"),
        ]
        for cells, reason in cases:
            with self.subTest(cells=cells):
                analysis = self.analyse_one(row("new@example.com", **cells))
                self.assertEqual((analysis.status, analysis.facts["invalid"]), ("invalid", reason))

    def test_an_existing_member_does_not_need_the_name_cells(self):
        analysis = self.analyse_one(row("ada@example.com", First_Name=None, Last_Name=None, Organization="Engines"))

        self.assertEqual((analysis.status, analysis.conflict), ("ready_update", ""))

    def test_invalid_rows_keep_their_warnings(self):
        analysis = self.analyse_one(row(None, Primary_Verified="maybe"))

        self.assertEqual(analysis.status, "invalid")
        self.assertEqual(
            analysis.warnings,
            [{"code": "V5", "text": "Primary Verified cell 'maybe' is not TRUE or FALSE; it was ignored"}],
        )

    def test_invalid_rows_are_never_grouped_as_repeats(self):
        analyses = self.analyse([row("bad-address"), row("bad-address", Organization="X")])

        self.assertEqual([(a.status, a.facts["group"]) for a in analyses], [("invalid", [])] * 2)

    def test_invalid_rows_are_not_imported(self):
        before = (Member.objects.count(), ContactEmail.objects.count())

        outcomes = self.apply([row(None), row("not-an-email"), row("new@example.com", Last_Name=None)])

        self.assertEqual([o.outcome for o in outcomes], ["not_imported"] * 3)
        self.assertEqual(
            [o.reason for o in outcomes],
            [
                "Missing primary email",
                "Primary Email 'not-an-email' is not a valid email address",
                "Missing last name",
            ],
        )
        self.assertEqual((Member.objects.count(), ContactEmail.objects.count()), before)


class SecondaryEmailWarningTests(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.secondary = self.email(self.ada, "ada.work@example.com")

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

    def test_a_shared_unlinked_secondary_goes_only_to_the_first_row_of_a_repeat_group(self):
        # The same person twice (C1): using row 3 instead of row 2 updates the member without the address.
        lab = ContactEmail.objects.create(member=None, email_address="lab@example.com", email_type="primary")
        rows = [
            row("ada@example.com", Secondary_Email="lab@example.com"),
            row("ada@example.com", Title="Countess", Secondary_Email="lab@example.com"),
        ]

        first, second = self.analyse(rows)

        self.assertEqual((first.conflict, second.conflict), ("duplicate_in_sheet", "duplicate_in_sheet"))
        self.assertEqual(second.warnings, [{"code": "V8", "text": V8_LAB}])
        outcomes = self.apply(rows, {2: ("skip", []), 3: ("use_row", [])})
        self.assertEqual([outcome.outcome for outcome in outcomes], ["skipped", "updated"])
        self.ada.refresh_from_db()
        lab.refresh_from_db()
        self.assertEqual((self.ada.title, lab.member), ("Countess", None))

    def test_only_the_first_row_adds_a_shared_new_secondary(self):
        rows = [
            row("one@example.com", Secondary_Email="shared.new@example.com", Phone_Number="209-555-0123"),
            row("two@example.com", Secondary_Email="shared.new@example.com", Phone_Number="209-555-0123"),
        ]

        first, second = self.apply(rows)

        self.assertEqual((first.outcome, second.outcome), ("created", "created"))
        self.assertEqual(ContactEmail.objects.get(email_address="shared.new@example.com").member, first.member)
        self.assertEqual(ContactPhone.objects.get(phone_number="2095550123").member, first.member)
        self.assertEqual(
            list(second.member.contact_emails.values_list("email_address", flat=True)), ["two@example.com"]
        )
        self.assertFalse(second.member.contact_phones.exists())


class PhoneWarningTests(ImportTestCase):
    def test_v4_a_number_that_is_not_a_10_digit_us_number(self):
        cases = {
            "12345": "+12345",
            "+44 20 7946 0958": "+442079460958",
            "123-456-7890": "+1234567890",
            "209-555-01011": "+20955501011",
        }
        for cell, e164 in cases.items():
            with self.subTest(cell=cell):
                analysis = self.analyse_one(row("ada@example.com", Phone_Number=cell))
                text = f"Phone Number {e164} is not a 10-digit US number; ignored"
                self.assertEqual(analysis.warnings, [{"code": "V4", "text": text}])
                self.assertEqual(analysis.status, "no_change")

    def test_us_numbers_in_any_format(self):
        for cell in ("2095550101", "(209) 555-0101", "+1 209 555 0101", "1-209-555-0101", "209.555.0101"):
            with self.subTest(cell=cell):
                analysis = self.analyse_one(row("new@example.com", Phone_Number=cell))
                self.assertEqual(analysis.warnings, [])

    def test_v8_the_same_new_number_in_two_rows(self):
        rows = [
            row("one@example.com", Phone_Number="2095550123"),
            row("two@example.com", Phone_Number="(209) 555-0123"),
        ]

        first, second = self.analyse(rows)

        self.assertEqual(first.warnings, [])
        self.assertEqual(
            second.warnings,
            [
                {
                    "code": "V8",
                    "text": "Phone Number +12095550123 is also in row 2; only that row can add it; if that row is skipped, no row adds it",
                }
            ],
        )

    def test_a_stored_number_in_two_rows_is_not_v8(self):
        self.phone(self.ada, "2095550101")
        rows = [row("one@example.com", Phone_Number="2095550101"), row("two@example.com", Phone_Number="2095550101")]

        analyses = self.analyse(rows)

        self.assertEqual([a.warnings for a in analyses], [[], []])

    def test_a_v4_cell_reads_as_a_missing_column(self):
        phone = self.phone(self.ada, "2095550101", verified=True)

        analysis = self.analyse_one(row("ada@example.com", Phone_Number="12345"))
        (outcome,) = self.apply([row("ada@example.com", Phone_Number="12345")])

        self.assertEqual(analysis.risky, {})
        self.assertEqual(outcome.outcome, "no_change")
        self.assertTrue(ContactPhone.objects.filter(pk=phone.pk, verified=True).exists())


class CellWarningOrderTests(ImportTestCase):
    def test_cell_warnings_come_before_the_cells_set_aside(self):
        headers = [*HEADERS, "When Started"]
        cells_row = [
            *row("new@example.com", Primary_Verified="maybe", Secondary_Email="bad@", Phone_Number="1"),
            "someday",
        ]

        analysis = self.analyse_one(cells_row, headers)

        self.assertEqual(codes(analysis), ["V5", "V6", "V2", "V4"])
        self.assertEqual(analysis.status, "ready_create")

    def test_a_row_with_a_cell_set_aside_is_still_imported(self):
        (outcome,) = self.apply([row("new@example.com", Secondary_Email="bad@")])

        self.assertEqual(outcome.outcome, "created")
        self.assertEqual(
            list(outcome.member.contact_emails.values_list("email_address", flat=True)), ["new@example.com"]
        )
