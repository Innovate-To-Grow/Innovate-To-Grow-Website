from io import BytesIO

from django.test import TestCase

from authn.models import ContactEmail, Member
from authn.services.import_members import import_members_from_excel

try:
    from openpyxl import Workbook
except ImportError:  # pragma: no cover - test environment should include openpyxl
    Workbook = None


class ImportMembersExcelTests(TestCase):
    def _build_workbook(self, rows: list[list[str]]):
        if Workbook is None:
            self.fail("openpyxl is required for import tests")

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.append(["Primary Email", "First Name", "Last Name", "Organization"])
        for row in rows:
            worksheet.append(row)

        payload = BytesIO()
        workbook.save(payload)
        payload.seek(0)
        return payload

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
