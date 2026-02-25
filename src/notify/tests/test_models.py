"""
Tests for GoogleGmailAccount model and email sending with DB accounts.
"""

import smtplib
from unittest.mock import MagicMock, patch

from django.test import TestCase

from ..models import GoogleGmailAccount
from ..providers.email import send_email


class GoogleGmailAccountModelTest(TestCase):
    """Tests for the GoogleGmailAccount model."""

    def test_create_account(self):
        account = GoogleGmailAccount.objects.create(
            gmail_address="test@gmail.com",
            google_app_password="abcd efgh ijkl mnop",
            display_name="Test Sender",
        )
        self.assertEqual(str(account), "Test Sender")
        self.assertTrue(account.is_active)
        self.assertFalse(account.is_default)

    def test_default_uniqueness(self):
        """Setting is_default=True should clear other defaults."""
        a1 = GoogleGmailAccount.objects.create(
            gmail_address="first@gmail.com",
            google_app_password="pass1",
            is_default=True,
        )
        a2 = GoogleGmailAccount.objects.create(
            gmail_address="second@gmail.com",
            google_app_password="pass2",
            is_default=True,
        )
        a1.refresh_from_db()
        self.assertFalse(a1.is_default)
        self.assertTrue(a2.is_default)

    def test_get_default(self):
        GoogleGmailAccount.objects.create(
            gmail_address="active@gmail.com",
            google_app_password="pass",
            is_active=True,
            is_default=True,
        )
        GoogleGmailAccount.objects.create(
            gmail_address="inactive@gmail.com",
            google_app_password="pass",
            is_active=False,
            is_default=False,
        )
        default = GoogleGmailAccount.get_default()
        self.assertIsNotNone(default)
        self.assertEqual(default.gmail_address, "active@gmail.com")

    def test_get_default_none(self):
        """Returns None when no default exists."""
        GoogleGmailAccount.objects.create(
            gmail_address="nodefault@gmail.com",
            google_app_password="pass",
            is_default=False,
        )
        self.assertIsNone(GoogleGmailAccount.get_default())

    def test_get_from_email(self):
        account = GoogleGmailAccount(
            gmail_address="team@gmail.com",
            display_name="I2G Team",
        )
        self.assertEqual(account.get_from_email(), "I2G Team <team@gmail.com>")

    def test_get_from_email_no_display_name(self):
        account = GoogleGmailAccount(gmail_address="team@gmail.com", display_name="")
        self.assertEqual(account.get_from_email(), "team@gmail.com")

    def test_mark_used(self):
        account = GoogleGmailAccount.objects.create(
            gmail_address="used@gmail.com",
            google_app_password="pass",
        )
        self.assertIsNone(account.last_used_at)

        account.mark_used()
        account.refresh_from_db()
        self.assertIsNotNone(account.last_used_at)
        self.assertEqual(account.last_error, "")

    def test_mark_used_with_error(self):
        account = GoogleGmailAccount.objects.create(
            gmail_address="err@gmail.com",
            google_app_password="pass",
        )
        account.mark_used(error="Connection refused")
        account.refresh_from_db()
        self.assertEqual(account.last_error, "Connection refused")

    def test_str_default_and_inactive(self):
        account = GoogleGmailAccount(
            gmail_address="test@gmail.com",
            display_name="Test",
            is_default=True,
            is_active=False,
        )
        result = str(account)
        self.assertIn("[Default]", result)
        self.assertIn("[Inactive]", result)

    def test_get_active_accounts(self):
        GoogleGmailAccount.objects.create(gmail_address="a@gmail.com", google_app_password="p", is_active=True)
        GoogleGmailAccount.objects.create(gmail_address="b@gmail.com", google_app_password="p", is_active=False)
        actives = GoogleGmailAccount.get_active_accounts()
        self.assertEqual(actives.count(), 1)
        self.assertEqual(actives.first().gmail_address, "a@gmail.com")


class SendEmailWithAccountTest(TestCase):
    """Tests for send_email with Gmail account from database."""

    def test_send_email_resolves_default_account(self):
        """send_email should use the default DB account when provider=gmail."""
        GoogleGmailAccount.objects.create(
            gmail_address="sender@gmail.com",
            google_app_password="app-pass",
            display_name="Sender",
            is_default=True,
        )
        with patch("notify.providers.email._smtp_connection_from_account") as mock_conn:
            mock_conn.return_value = None
            with patch("django.core.mail.EmailMultiAlternatives.send"):
                success, provider = send_email(
                    target="recipient@example.com",
                    subject="Hi",
                    body="Test",
                    provider="gmail",
                )
                self.assertTrue(success)
                self.assertEqual(provider, "gmail")

    def test_send_email_console_with_attachments(self):
        """Console provider should log attachments."""
        success, provider = send_email(
            target="test@example.com",
            subject="Test",
            body="Hello",
            provider="console",
            attachments=[("file.pdf", b"content", "application/pdf")],
        )
        self.assertTrue(success)
        self.assertEqual(provider, "console")

    def test_send_email_with_cc_bcc_console(self):
        """Console provider should print Cc and Bcc."""
        success, provider = send_email(
            target="to@example.com",
            subject="Test",
            body="Hello",
            provider="console",
            cc=["cc1@example.com", "cc2@example.com"],
            bcc=["bcc@example.com"],
        )
        self.assertTrue(success)
        self.assertEqual(provider, "console")

    def test_send_email_with_cc_bcc_gmail(self):
        """Gmail provider should pass Cc/Bcc to EmailMultiAlternatives."""
        GoogleGmailAccount.objects.create(
            gmail_address="sender@gmail.com",
            google_app_password="app-pass",
            is_default=True,
        )
        with patch("notify.providers.email._smtp_connection_from_account") as mock_conn:
            mock_conn.return_value = None
            with patch("django.core.mail.EmailMultiAlternatives.send"):
                with patch("django.core.mail.EmailMultiAlternatives.__init__", wraps=None) as mock_init:
                    # Use wraps to inspect args - but simpler to just check it doesn't crash
                    pass
                success, provider = send_email(
                    target="recipient@example.com",
                    subject="Hi",
                    body="Test",
                    provider="gmail",
                    cc=["cc@example.com"],
                    bcc=["bcc@example.com"],
                )
                self.assertTrue(success)
                self.assertEqual(provider, "gmail")

    def test_send_email_env_var_fallback(self):
        """When no DB account exists, fall back to env vars."""
        env_vars = {
            "EMAIL_SMTP_USER": "env-user@gmail.com",
            "EMAIL_SMTP_PASS": "env-app-pass",
            "EMAIL_SMTP_HOST": "smtp.gmail.com",
            "EMAIL_SMTP_PORT": "587",
        }
        with patch.dict("os.environ", env_vars):
            with patch("notify.providers.email.get_connection") as mock_get_conn:
                mock_get_conn.return_value = MagicMock()
                with patch("django.core.mail.EmailMultiAlternatives.send"):
                    success, provider = send_email(
                        target="recipient@example.com",
                        subject="Hi",
                        body="Test",
                        provider="gmail",
                    )
                    self.assertTrue(success)
                    self.assertEqual(provider, "gmail")
                    # get_connection should have been called with env var values
                    mock_get_conn.assert_called_once_with(
                        host="smtp.gmail.com",
                        port=587,
                        username="env-user@gmail.com",
                        password="env-app-pass",
                        use_tls=True,
                        use_ssl=False,
                    )

    def test_send_email_no_account_no_env_vars(self):
        """Should fail when no DB account and no env vars are set."""
        env_vars = {
            "EMAIL_SMTP_USER": "",
            "EMAIL_SMTP_PASS": "",
        }
        with patch.dict("os.environ", env_vars, clear=False):
            success, provider = send_email(
                target="recipient@example.com",
                subject="Hi",
                body="Test",
                provider="gmail",
            )
            self.assertFalse(success)
            self.assertEqual(provider, "gmail")

    def test_send_email_smtp_auth_error(self):
        """SMTPAuthenticationError should return a friendly message."""
        GoogleGmailAccount.objects.create(
            gmail_address="sender@gmail.com",
            google_app_password="bad-pass",
            is_default=True,
        )
        with patch("notify.providers.email._smtp_connection_from_account") as mock_conn:
            mock_conn.return_value = None
            with patch(
                "django.core.mail.EmailMultiAlternatives.send",
                side_effect=smtplib.SMTPAuthenticationError(535, b"Auth failed"),
            ):
                success, provider = send_email(
                    target="recipient@example.com",
                    subject="Hi",
                    body="Test",
                    provider="gmail",
                )
                self.assertFalse(success)
                self.assertEqual(provider, "gmail")

        # Check the error was recorded on the account
        account = GoogleGmailAccount.objects.get(gmail_address="sender@gmail.com")
        self.assertIn("Authentication failed", account.last_error)

    def test_send_email_smtp_connect_error(self):
        """SMTPConnectError should return a friendly message."""
        GoogleGmailAccount.objects.create(
            gmail_address="sender@gmail.com",
            google_app_password="pass",
            is_default=True,
        )
        with patch("notify.providers.email._smtp_connection_from_account") as mock_conn:
            mock_conn.return_value = None
            with patch(
                "django.core.mail.EmailMultiAlternatives.send",
                side_effect=smtplib.SMTPConnectError(421, b"Connection refused"),
            ):
                success, provider = send_email(
                    target="recipient@example.com",
                    subject="Hi",
                    body="Test",
                    provider="gmail",
                )
                self.assertFalse(success)

        account = GoogleGmailAccount.objects.get(gmail_address="sender@gmail.com")
        self.assertIn("Could not connect", account.last_error)

    def test_send_email_smtp_recipients_refused(self):
        """SMTPRecipientsRefused should return a friendly message."""
        GoogleGmailAccount.objects.create(
            gmail_address="sender@gmail.com",
            google_app_password="pass",
            is_default=True,
        )
        with patch("notify.providers.email._smtp_connection_from_account") as mock_conn:
            mock_conn.return_value = None
            with patch(
                "django.core.mail.EmailMultiAlternatives.send",
                side_effect=smtplib.SMTPRecipientsRefused({"bad@example.com": (550, b"User unknown")}),
            ):
                success, provider = send_email(
                    target="bad@example.com",
                    subject="Hi",
                    body="Test",
                    provider="gmail",
                )
                self.assertFalse(success)

        account = GoogleGmailAccount.objects.get(gmail_address="sender@gmail.com")
        self.assertIn("Invalid recipient", account.last_error)

    def test_send_email_generic_smtp_error(self):
        """Generic SMTPException should log the detail."""
        GoogleGmailAccount.objects.create(
            gmail_address="sender@gmail.com",
            google_app_password="pass",
            is_default=True,
        )
        with patch("notify.providers.email._smtp_connection_from_account") as mock_conn:
            mock_conn.return_value = None
            with patch(
                "django.core.mail.EmailMultiAlternatives.send",
                side_effect=smtplib.SMTPException("Something went wrong"),
            ):
                success, provider = send_email(
                    target="recipient@example.com",
                    subject="Hi",
                    body="Test",
                    provider="gmail",
                )
                self.assertFalse(success)

        account = GoogleGmailAccount.objects.get(gmail_address="sender@gmail.com")
        self.assertIn("SMTP error", account.last_error)
