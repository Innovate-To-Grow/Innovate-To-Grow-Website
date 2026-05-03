"""Tests for authn.services.email.send_email."""

from smtplib import SMTPAuthenticationError, SMTPServerDisconnected
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.utils import timezone

from authn.services.email.send_email import (
    _render_email_body,
    _send_via_ses,
    _send_via_smtp,
    send_admin_invitation_email,
    send_verification_email,
)


def _fake_config(**overrides):
    """Return a mock EmailServiceConfig with sensible defaults."""
    defaults = {
        "ses_configured": False,
        "ses_access_key_id": "",
        "ses_secret_access_key": "",
        "ses_region": "us-west-2",
        "ses_from_email": "test@example.com",
        "ses_from_name": "Test",
        "source_address": "Test <test@example.com>",
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_use_tls": True,
        "smtp_username": "user",
        "smtp_password": "pass",
    }
    defaults.update(overrides)
    config = MagicMock(**defaults)
    return config


class SendViaSesTests(TestCase):
    """Tests for the SES sending path."""

    def test_returns_false_when_not_configured(self):
        config = _fake_config(ses_configured=False)
        result = _send_via_ses(config=config, recipient="a@b.com", subject="Hi", html_body="<p>Hi</p>")
        self.assertFalse(result)

    @patch("authn.services.email.send_email.boto3")
    def test_returns_true_on_success(self, mock_boto3):
        config = _fake_config(ses_configured=True, ses_access_key_id="key", ses_secret_access_key="secret")
        result = _send_via_ses(config=config, recipient="a@b.com", subject="Hi", html_body="<p>Hi</p>")
        self.assertTrue(result)
        mock_boto3.client.return_value.send_email.assert_called_once()

    @patch("authn.services.email.send_email.boto3")
    def test_returns_false_on_client_error(self, mock_boto3):
        from botocore.exceptions import ClientError

        mock_boto3.client.return_value.send_email.side_effect = ClientError(
            {"Error": {"Code": "MessageRejected", "Message": "boom"}}, "SendEmail"
        )
        config = _fake_config(ses_configured=True, ses_access_key_id="key", ses_secret_access_key="secret")
        result = _send_via_ses(config=config, recipient="a@b.com", subject="Hi", html_body="<p>Hi</p>")
        self.assertFalse(result)


class SendViaSmtpTests(TestCase):
    """Tests for the SMTP sending path with retry and timeout."""

    @patch("django.core.mail.get_connection")
    def test_success_on_first_attempt(self, mock_get_conn):
        config = _fake_config()
        _send_via_smtp(config=config, recipient="a@b.com", subject="Hi", html_body="<p>Hi</p>")
        mock_get_conn.assert_called_once()
        call_kwargs = mock_get_conn.call_args.kwargs
        self.assertEqual(call_kwargs["timeout"], 15)

    @patch("authn.services.email.send_email.time.sleep")
    @patch("authn.services.email.send_email.EmailMessage")
    @patch("django.core.mail.get_connection")
    def test_retries_on_transient_failure(self, mock_get_conn, MockMsg, mock_sleep):
        """SMTP should retry once after a transient connection failure."""
        instance = MockMsg.return_value
        instance.send.side_effect = [SMTPServerDisconnected("reset"), None]

        config = _fake_config()
        _send_via_smtp(config=config, recipient="a@b.com", subject="Hi", html_body="<p>Hi</p>")

        self.assertEqual(instance.send.call_count, 2)
        mock_sleep.assert_called_once_with(1)

    @patch("authn.services.email.send_email.time.sleep")
    @patch("authn.services.email.send_email.EmailMessage")
    @patch("django.core.mail.get_connection")
    def test_raises_after_all_retries_exhausted(self, mock_get_conn, MockMsg, mock_sleep):
        """If all SMTP retries fail, the last exception should be raised."""
        instance = MockMsg.return_value
        instance.send.side_effect = SMTPAuthenticationError(535, b"auth failed")

        config = _fake_config()
        with self.assertRaises(SMTPAuthenticationError):
            _send_via_smtp(config=config, recipient="a@b.com", subject="Hi", html_body="<p>Hi</p>")

        self.assertEqual(instance.send.call_count, 2)
        mock_sleep.assert_called_once_with(1)


class SendVerificationEmailTests(TestCase):
    """Tests for the full send_verification_email flow."""

    @override_settings(FRONTEND_URL="https://www.example.com")
    def test_render_body_includes_register_continue_link(self):
        html = _render_email_body(
            recipient="new-user@example.com",
            code="123456",
            purpose="register",
            link_flow="register",
            link_source="register",
        )

        self.assertIn("Continue Registration", html)
        self.assertIn("email-auth-link?flow=register", html)
        self.assertIn("source=register", html)
        self.assertIn("email=new-user%40example.com", html)
        self.assertIn("code=123456", html)

    @override_settings(FRONTEND_URL="https://www.example.com")
    def test_render_body_includes_login_link_for_public_auth(self):
        html = _render_email_body(
            recipient="member@example.com",
            code="123456",
            purpose="login",
            link_flow="auth",
            link_source="login",
        )

        self.assertIn("Sign In to Your Account", html)
        self.assertIn("email-auth-link?flow=auth", html)
        self.assertIn("source=login", html)
        self.assertIn("email=member%40example.com", html)

    @override_settings(FRONTEND_URL="https://www.example.com")
    def test_render_body_omits_public_link_for_admin_login(self):
        html = _render_email_body(
            recipient="admin@example.com",
            code="123456",
            purpose="admin_login",
        )

        self.assertNotIn("email-auth-link?", html)
        self.assertNotIn("Continue Registration", html)
        self.assertNotIn("Sign In to Your Account", html)

    @patch("authn.services.email.send_email._send_via_smtp")
    @patch("authn.services.email.send_email._send_via_ses", return_value=True)
    @patch("authn.services.email.send_email._load_config")
    def test_ses_success_skips_smtp(self, mock_config, mock_ses, mock_smtp):
        mock_config.return_value = _fake_config(ses_configured=True)
        send_verification_email(recipient="a@b.com", code="123456", purpose="admin_login")
        mock_ses.assert_called_once()
        mock_smtp.assert_not_called()

    @patch("authn.services.email.send_email._send_via_smtp")
    @patch("authn.services.email.send_email._send_via_ses", return_value=False)
    @patch("authn.services.email.send_email._load_config")
    def test_ses_failure_falls_back_to_smtp(self, mock_config, mock_ses, mock_smtp):
        mock_config.return_value = _fake_config(ses_configured=True)
        send_verification_email(recipient="a@b.com", code="123456", purpose="admin_login")
        mock_ses.assert_called_once()
        mock_smtp.assert_called_once()

    @patch("authn.services.email.send_email._send_via_smtp")
    @patch("authn.services.email.send_email._send_via_ses")
    @patch("authn.services.email.send_email._load_config")
    def test_ses_not_configured_goes_straight_to_smtp(self, mock_config, mock_ses, mock_smtp):
        mock_config.return_value = _fake_config(ses_configured=False)
        send_verification_email(recipient="a@b.com", code="123456", purpose="admin_login")
        mock_ses.assert_not_called()
        mock_smtp.assert_called_once()

    @patch("authn.services.email.send_email._send_via_smtp", side_effect=SMTPAuthenticationError(535, b"bad"))
    @patch("authn.services.email.send_email._load_config")
    def test_both_fail_raises(self, mock_config, mock_smtp):
        mock_config.return_value = _fake_config(ses_configured=False)
        with self.assertRaises(SMTPAuthenticationError):
            send_verification_email(recipient="a@b.com", code="123456", purpose="admin_login")


class SendAdminInvitationEmailTests(TestCase):
    """Tests for the admin invitation email flow."""

    def _invitation(self):
        invitation = MagicMock()
        invitation.email = "new-admin@example.com"
        invitation.expires_at = timezone.now() + timezone.timedelta(days=7)
        invitation.invited_by = None
        invitation.message = "Please help manage the spring event."
        invitation.get_acceptance_url.return_value = "https://admin.example.com/authn/invite/token/"
        invitation.get_role_display.return_value = "Admin"
        return invitation

    @patch("authn.services.email.send_email._send_via_smtp")
    @patch("authn.services.email.send_email._send_via_ses")
    @patch("authn.services.email.send_email._load_config")
    def test_smtp_email_includes_acceptance_link(self, mock_config, mock_ses, mock_smtp):
        mock_config.return_value = _fake_config(ses_configured=False)
        invitation = self._invitation()

        send_admin_invitation_email(invitation=invitation)

        mock_ses.assert_not_called()
        mock_smtp.assert_called_once()
        call_kwargs = mock_smtp.call_args.kwargs
        self.assertEqual(call_kwargs["recipient"], "new-admin@example.com")
        self.assertIn("invited to join", call_kwargs["subject"])
        self.assertIn("https://admin.example.com/authn/invite/token/", call_kwargs["html_body"])
        self.assertIn("Please help manage the spring event.", call_kwargs["html_body"])

    @patch("authn.services.email.send_email._send_via_smtp")
    @patch("authn.services.email.send_email._send_via_ses", return_value=True)
    @patch("authn.services.email.send_email._load_config")
    def test_ses_success_skips_smtp(self, mock_config, mock_ses, mock_smtp):
        mock_config.return_value = _fake_config(ses_configured=True)

        send_admin_invitation_email(invitation=self._invitation())

        mock_ses.assert_called_once()
        mock_smtp.assert_not_called()
