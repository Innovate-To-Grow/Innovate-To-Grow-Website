"""The import review ignores the Phone Verified column (decided on 2026-11-12, #726).

A verified phone number is a sign-in factor, so only the member's own one-time code may produce one. The reader lists
the column as "Not imported" with one note, a new member's number is planned and written unverified, and a stored
number keeps its status: the review never offers to verify or un-verify a number (no R6/R9 item), a posted tick for one
is forged, and the guarded writes refuse a "verified" flag on a number even if a plan carried one.
"""

from apps.authn.models import ContactPhone, MemberImportRow
from apps.authn.services.members.import_.review import apply_batch
from apps.authn.services.members.import_.review.staging.selection import plan_for
from apps.authn.services.members.import_.workbook.columns import ADMIN_IGNORED, PHONE_VERIFIED_IGNORED
from apps.authn.tests.services.members.import_.helpers import HEADERS, ImportTestCase, read, row

# Every kind of cell a Phone Verified column may hold: text and booleans in both directions, garbage, and blank.
CELLS = ("TRUE", "FALSE", "Yes", "no", "1", "0", True, False, 1, 0, "maybe", "N/A", 2, "", None)


def _number(index: int) -> str:
    return f"20955502{index:02d}"


class ReaderTests(ImportTestCase):
    def test_the_column_is_listed_as_not_imported_with_one_note(self):
        sheet = read(HEADERS, [row("ada@example.com", Phone_Verified="TRUE"), row("bob@example.com", Phone_Verified=1)])

        self.assertIn("Phone Verified", sheet.columns["informational"])
        self.assertNotIn("Phone Verified", sheet.columns["recognised"])
        self.assertNotIn("phone_verified", sheet.columns["keys"])
        # HEADERS also has the old Staff column, which the import ignores with its own note.
        self.assertEqual(sheet.columns["notes"], [PHONE_VERIFIED_IGNORED, ADMIN_IGNORED])
        self.assertEqual(sheet.warnings, [])
        for parsed in sheet.rows:
            self.assertNotIn("phone_verified", parsed)
            self.assertNotIn("phone_verified", parsed["raw"])
            self.assertEqual(parsed["warnings"], [])

    def test_every_spelling_is_ignored_and_two_such_columns_do_not_warn(self):
        sheet = read(
            ["Primary Email", "Phone Number Verified", "phone_verified"], [["ada@example.com", "TRUE", "FALSE"]]
        )

        self.assertEqual(sheet.columns["informational"], ["Phone Number Verified", "phone_verified"])
        self.assertEqual(sheet.columns["notes"], [PHONE_VERIFIED_IGNORED])
        self.assertEqual(sheet.warnings, [])

    def test_without_the_column_there_is_no_note(self):
        sheet = read(
            ["Primary Email", "First Name", "Last Name", "Phone Number"],
            [["ada@example.com", "Ada", "Lovelace", "2095550101"]],
        )

        self.assertEqual(sheet.columns["notes"], [])
        self.assertNotIn("Phone Verified", sheet.columns["informational"])


class NewMemberNumberTests(ImportTestCase):
    def _rows(self):
        return [
            row(
                f"new{index}@example.com",
                First_Name="New",
                Last_Name=f"Member{index}",
                Phone_Number=_number(index),
                Phone_Verified=cell,
            )
            for index, cell in enumerate(CELLS)
        ]

    def test_every_cell_value_plans_an_unverified_number(self):
        for index, analysis in enumerate(self.analyse(self._rows())):
            with self.subTest(cell=CELLS[index]):
                plan = plan_for(analysis, analysis.default, [])

                self.assertEqual((analysis.status, analysis.risky), ("ready_create", {}))
                self.assertIn(f"Phone +1{_number(index)} (unverified, not subscribed)", plan.changes)
                (add_phone,) = [op for op in plan.ops if op.kind == "add_phone"]
                self.assertNotIn("verified", add_phone.data)

    def test_every_cell_value_writes_an_unverified_number(self):
        outcomes = self.apply(self._rows())

        self.assertEqual({outcome.outcome for outcome in outcomes}, {"created"})
        self.assertEqual(ContactPhone.objects.count(), len(CELLS))
        self.assertFalse(ContactPhone.objects.filter(verified=True).exists())
        self.assertFalse(any("Phone Verified" in note for outcome in outcomes for note in outcome.notes))

    def test_a_value_left_in_rows_staged_before_the_change_is_never_read(self):
        """A batch staged by the old code stored the cell in its values: the apply re-plans and ignores it."""
        uploader = self.member("Up", "Loader", "uploader@example.com", is_staff=True)
        batch = self.stage(
            [row("nina@example.com", First_Name="Nina", Last_Name="New", Phone_Number="2095550177")], uploader
        )
        stored = batch.rows.get()
        stored.values = {**stored.values, "phone_verified": True}
        stored.save(update_fields=["values"])

        result = apply_batch(batch.pk, user=uploader, version=batch.choices_version, ctx=self.context())

        self.assertEqual(result.status, "applied")
        phone = ContactPhone.objects.get(phone_number="2095550177")
        self.assertEqual((phone.member.first_name, phone.verified), ("Nina", False))
        self.assertIn("Phone +12095550177 (unverified, not subscribed)", MemberImportRow.objects.get().outcome_detail)
