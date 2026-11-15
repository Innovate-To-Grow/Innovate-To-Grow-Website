from apps.authn.models import ContactPhone
from apps.authn.tests.services.members.import_.helpers import HEADERS, ImportTestCase, row
from apps.authn.tests.services.members.import_.reading.test_validation import codes


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
