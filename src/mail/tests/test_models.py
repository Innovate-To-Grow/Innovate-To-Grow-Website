"""Tests for mail app models."""

from django.test import TestCase

from mail.models import EmailLog, GoogleAccount

FAKE_SERVICE_JSON = '{"type":"service_account","project_id":"test","private_key":"key","client_email":"sa@test.iam.gserviceaccount.com"}'


class GoogleAccountModelTest(TestCase):
    """Tests for GoogleAccount model."""

    def test_create_account(self):
        account = GoogleAccount.objects.create(
            email="test@example.com",
            display_name="Test",
            service_account_json=FAKE_SERVICE_JSON,
            is_active=True,
        )
        self.assertEqual(str(account), "Test")
        self.assertTrue(account.is_active)
        self.assertIsNotNone(account.id)

    def test_singleton_active_pattern(self):
        """Only one account should be active at a time."""
        a1 = GoogleAccount.objects.create(
            email="a1@example.com",
            service_account_json=FAKE_SERVICE_JSON,
            is_active=True,
        )
        a2 = GoogleAccount.objects.create(
            email="a2@example.com",
            service_account_json=FAKE_SERVICE_JSON,
            is_active=True,
        )
        a1.refresh_from_db()
        self.assertFalse(a1.is_active)
        self.assertTrue(a2.is_active)

    def test_get_active(self):
        GoogleAccount.objects.create(
            email="inactive@example.com",
            service_account_json=FAKE_SERVICE_JSON,
            is_active=False,
        )
        active = GoogleAccount.objects.create(
            email="active@example.com",
            service_account_json=FAKE_SERVICE_JSON,
            is_active=True,
        )
        self.assertEqual(GoogleAccount.get_active(), active)

    def test_get_active_returns_none(self):
        self.assertIsNone(GoogleAccount.get_active())

    def test_mark_used(self):
        account = GoogleAccount.objects.create(
            email="test@example.com",
            service_account_json=FAKE_SERVICE_JSON,
        )
        account.mark_used(error="test error")
        account.refresh_from_db()
        self.assertIsNotNone(account.last_used_at)
        self.assertEqual(account.last_error, "test error")

    def test_mark_used_clears_error(self):
        account = GoogleAccount.objects.create(
            email="test@example.com",
            service_account_json=FAKE_SERVICE_JSON,
            last_error="old error",
        )
        account.mark_used()
        account.refresh_from_db()
        self.assertEqual(account.last_error, "")

    def test_soft_delete(self):
        account = GoogleAccount.objects.create(
            email="test@example.com",
            service_account_json=FAKE_SERVICE_JSON,
        )
        account.delete()
        self.assertEqual(GoogleAccount.objects.count(), 0)
        self.assertEqual(GoogleAccount.all_objects.count(), 1)

    def test_get_active_excludes_deleted(self):
        account = GoogleAccount.objects.create(
            email="test@example.com",
            service_account_json=FAKE_SERVICE_JSON,
            is_active=True,
        )
        account.delete()
        self.assertIsNone(GoogleAccount.get_active())

    def test_str_inactive(self):
        account = GoogleAccount(email="test@example.com", is_active=False)
        self.assertEqual(str(account), "test@example.com [Inactive]")

    def test_str_with_display_name(self):
        account = GoogleAccount(email="test@example.com", display_name="ITG", is_active=True)
        self.assertEqual(str(account), "ITG")


class EmailLogModelTest(TestCase):
    """Tests for EmailLog model."""

    def setUp(self):
        self.account = GoogleAccount.objects.create(
            email="test@example.com",
            service_account_json=FAKE_SERVICE_JSON,
        )

    def test_create_log(self):
        log = EmailLog.objects.create(
            account=self.account,
            action=EmailLog.Action.SEND,
            status=EmailLog.Status.SUCCESS,
            subject="Test Subject",
            recipients="user@example.com",
        )
        self.assertEqual(str(log), "Send - Test Subject")

    def test_ordering(self):
        """Logs should be ordered by newest first."""
        log1 = EmailLog.objects.create(
            account=self.account,
            action=EmailLog.Action.SEND,
            status=EmailLog.Status.SUCCESS,
            subject="First",
        )
        log2 = EmailLog.objects.create(
            account=self.account,
            action=EmailLog.Action.READ,
            status=EmailLog.Status.SUCCESS,
            subject="Second",
        )
        logs = list(EmailLog.objects.all())
        self.assertEqual(logs[0], log2)
        self.assertEqual(logs[1], log1)

    def test_str_no_subject(self):
        log = EmailLog(action=EmailLog.Action.READ, status=EmailLog.Status.SUCCESS)
        self.assertEqual(str(log), "Read - (no subject)")

    def test_account_cascade_set_null(self):
        log = EmailLog.objects.create(
            account=self.account,
            action=EmailLog.Action.SEND,
            status=EmailLog.Status.SUCCESS,
        )
        self.account.hard_delete()
        log.refresh_from_db()
        self.assertIsNone(log.account)
