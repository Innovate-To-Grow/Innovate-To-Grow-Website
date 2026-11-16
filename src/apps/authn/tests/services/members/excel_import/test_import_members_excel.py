from io import BytesIO
from unittest.mock import patch

from django.test import TestCase

from apps.authn.models import ContactEmail, Member
from apps.authn.services.members.import_ import import_members_from_excel

try:
    from openpyxl import Workbook
except ImportError:  # pragma: no cover - test environment should include openpyxl
    Workbook = None


class _ImportMembersExcelCase(TestCase):
    HEADERS = ["Primary Email", "First Name", "Last Name", "Organization"]

    def _build_workbook(self, rows: list[list[str]], headers: list[str] | None = None):
        if Workbook is None:
            self.fail("openpyxl is required for import tests")

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.append(headers if headers is not None else self.HEADERS)
        for row in rows:
            worksheet.append(row)

        payload = BytesIO()
        workbook.save(payload)
        payload.seek(0)
        return payload

    def _build_full_workbook(self, rows: list[list]):
        headers = [
            "Primary Email",
            "First Name",
            "Last Name",
            "Secondary Email",
            "Phone Number",
            "Organization",
        ]
        return self._build_workbook(rows, headers=headers)


class ImportMembersExcelTests(_ImportMembersExcelCase):
    def test_missing_last_name_skips_new_member(self):
        workbook = self._build_workbook(
            [
                ["new-member@example.com", "Ada", "", "Acme"],
            ]
        )

        result = import_members_from_excel(workbook)

        self.assertTrue(result.success)
        self.assertEqual(result.created_count, 0)
        self.assertEqual(result.skipped_count, 1)
        self.assertIn("Row 2: Missing last name", result.errors)
        self.assertFalse(ContactEmail.objects.filter(email_address="new-member@example.com").exists())

    def test_update_existing_does_not_clear_names_when_import_row_leaves_them_blank(self):
        member = Member.objects.create_user(
            password="StrongPass123!",
            first_name="Existing",
            last_name="Member",
            organization="Original Org",
            is_active=True,
        )
        ContactEmail.objects.create(
            member=member,
            email_address="existing@example.com",
            email_type="primary",
            verified=True,
        )

        workbook = self._build_workbook(
            [
                ["existing@example.com", "", "", "Updated Org"],
            ]
        )

        result = import_members_from_excel(workbook, update_existing=True)

        member.refresh_from_db()
        self.assertTrue(result.success)
        self.assertEqual(result.updated_count, 1)
        self.assertEqual(member.first_name, "Existing")
        self.assertEqual(member.last_name, "Member")
        self.assertEqual(member.organization, "Updated Org")

    def test_openpyxl_missing_returns_error(self):
        with patch("apps.authn.services.members.import_.reader.load_workbook", None):
            result = import_members_from_excel(BytesIO(b""))
        self.assertFalse(result.success)
        self.assertIn("openpyxl library not installed. Please run: pip install openpyxl", result.errors)

    def test_empty_file_returns_error(self):
        if Workbook is None:
            self.fail("openpyxl required")
        workbook = Workbook()
        # delete default rows by leaving sheet empty: iter_rows yields nothing
        payload = BytesIO()
        workbook.save(payload)
        payload.seek(0)
        result = import_members_from_excel(payload)
        self.assertFalse(result.success)
        self.assertIn("Excel file is empty", result.errors)

    def test_missing_primary_email_column_returns_error(self):
        workbook = self._build_workbook([["Ada", "Lovelace"]], headers=["First Name", "Last Name"])
        result = import_members_from_excel(workbook)
        self.assertFalse(result.success)
        self.assertIn("Excel file must contain a 'Primary Email' column", result.errors)

    def test_blank_rows_are_skipped(self):
        workbook = self._build_workbook(
            [
                [None, None, None, None],
                ["solo@example.com", "Ada", "Lovelace", "Acme"],
            ]
        )
        result = import_members_from_excel(workbook)
        self.assertTrue(result.success)
        self.assertEqual(result.created_count, 1)

    def test_missing_primary_email_in_row_skips(self):
        workbook = self._build_workbook([["", "Ada", "Lovelace", "Acme"]])
        result = import_members_from_excel(workbook)
        self.assertTrue(result.success)
        self.assertEqual(result.skipped_count, 1)
        self.assertIn("Row 2: Missing primary email", result.errors)

    def test_duplicate_email_within_file_skips_both_until_one_is_chosen(self):
        workbook = self._build_workbook(
            [
                ["dup@example.com", "Ada", "Lovelace", "Acme"],
                ["DUP@example.com", "Grace", "Hopper", "Navy"],
            ]
        )
        result = import_members_from_excel(workbook)
        self.assertTrue(result.success)
        self.assertEqual(result.created_count, 0)
        self.assertEqual(result.skipped_count, 2)
        self.assertTrue(all("The same person appears more than once in the sheet" in e for e in result.errors))

    def test_no_valid_parsed_rows_returns_early(self):
        workbook = self._build_workbook([["", "Ada", "Lovelace", "Acme"]])
        result = import_members_from_excel(workbook)
        # parsed_rows empty after skip -> returns result with skip recorded
        self.assertTrue(result.success)
        self.assertEqual(result.created_count, 0)

    def test_existing_member_skipped_when_update_disabled(self):
        member = Member.objects.create_user(password="StrongPass123!", first_name="Ex", last_name="Member")
        ContactEmail.objects.create(
            member=member, email_address="exists@example.com", email_type="primary", verified=True
        )
        workbook = self._build_workbook([["exists@example.com", "Ex", "Member", "NewOrg"]])
        result = import_members_from_excel(workbook, update_existing=False)
        self.assertTrue(result.success)
        self.assertEqual(result.created_count, 0)
        self.assertEqual(result.skipped_count, 1)
        self.assertTrue(any("the upload said to skip rows that match an existing member" in e for e in result.errors))

    def test_missing_first_name_skips_new_member(self):
        workbook = self._build_workbook([["nofn@example.com", "", "Lovelace", "Acme"]])
        result = import_members_from_excel(workbook)
        self.assertTrue(result.success)
        self.assertEqual(result.created_count, 0)
        self.assertEqual(result.skipped_count, 1)
        self.assertIn("Row 2: Missing first name", result.errors)
