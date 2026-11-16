"""Rows that cannot be imported, and the warnings (V2, V4–V8) that set a cell aside while the row is still imported."""

from apps.authn.models import ContactEmail, Member
from apps.authn.tests.services.members.import_.helpers import ImportTestCase, row


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
