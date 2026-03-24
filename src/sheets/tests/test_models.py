from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from sheets.models import SheetLink, SheetsAccount


class SheetsAccountTests(TestCase):
    def _make_account(self, email="test@example.com", is_active=True):
        return SheetsAccount.objects.create(
            email=email,
            display_name="Test",
            service_account_json='{"type": "service_account"}',
            is_active=is_active,
        )

    def test_single_active_enforcement(self):
        a1 = self._make_account("a1@example.com", is_active=True)
        a2 = self._make_account("a2@example.com", is_active=True)

        a1.refresh_from_db()
        self.assertFalse(a1.is_active)
        self.assertTrue(a2.is_active)

    def test_get_active_returns_active(self):
        self._make_account("inactive@example.com", is_active=False)
        active = self._make_account("active@example.com", is_active=True)

        result = SheetsAccount.get_active()
        self.assertEqual(result.pk, active.pk)

    def test_get_active_returns_none_when_none_active(self):
        self._make_account("inactive@example.com", is_active=False)
        self.assertIsNone(SheetsAccount.get_active())

    def test_mark_used_updates_metadata(self):
        account = self._make_account()
        self.assertIsNone(account.last_used_at)

        account.mark_used()
        account.refresh_from_db()
        self.assertIsNotNone(account.last_used_at)
        self.assertEqual(account.last_error, "")

    def test_mark_used_with_error(self):
        account = self._make_account()
        account.mark_used(error="API quota exceeded")
        account.refresh_from_db()
        self.assertEqual(account.last_error, "API quota exceeded")

    def test_str_active(self):
        account = self._make_account()
        self.assertEqual(str(account), "Test")

    def test_str_inactive(self):
        account = self._make_account(is_active=False)
        self.assertEqual(str(account), "Test [Inactive]")


class SheetLinkTests(TestCase):
    def setUp(self):
        self.account = SheetsAccount.objects.create(
            email="test@example.com",
            service_account_json='{"type": "service_account"}',
        )

    def test_get_sheet_range_both(self):
        ct = ContentType.objects.get_for_model(SheetsAccount)  # any model
        link = SheetLink.objects.create(
            name="Test",
            account=self.account,
            spreadsheet_id="abc",
            sheet_name="Sheet1",
            range_a1="A1:Z100",
            content_type=ct,
        )
        self.assertEqual(link.get_sheet_range(), "Sheet1!A1:Z100")

    def test_get_sheet_range_name_only(self):
        ct = ContentType.objects.get_for_model(SheetsAccount)
        link = SheetLink.objects.create(
            name="Test",
            account=self.account,
            spreadsheet_id="abc",
            sheet_name="Sheet1",
            content_type=ct,
        )
        self.assertEqual(link.get_sheet_range(), "Sheet1")

    def test_get_sheet_range_range_only(self):
        ct = ContentType.objects.get_for_model(SheetsAccount)
        link = SheetLink.objects.create(
            name="Test",
            account=self.account,
            spreadsheet_id="abc",
            range_a1="A1:Z100",
            content_type=ct,
        )
        self.assertEqual(link.get_sheet_range(), "A1:Z100")
