"""Tests for authn.services.email.send_email."""

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.utils import timezone

from authn.services.email.send_email import (
    _render_email_body,
    _send_via_ses,
    send_admin_invitation_email,
    send_verification_email,
)


def _fake_config(**overrides):
    """Return a mock EmailServiceConfig with sensible defaults."""
    defaults = {
        "ses_configured": False,
        "ses_from_email": "test@example.com",
        "ses_from_name": "Test",
        "source_address": "Test <test@example.com>",
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

    @patch("authn.services.email.send_email.transport.resolve_aws_credentials")
    @patch("authn.services.email.send_email.boto3")
    def test_returns_true_on_success(self, mock_boto3, mock_resolve):
        from core.services.aws.credentials import AwsCredentials

        mock_resolve.return_value = AwsCredentials(access_key_id="k", secret_access_key="s", region="us-west-2")
        config = _fake_config(ses_configured=True)
        result = _send_via_ses(config=config, recipient="a@b.com", subject="Hi", html_body="<p>Hi</p>")
        self.assertTrue(result)
        mock_boto3.client.return_value.send_email.assert_called_once()

    @patch("authn.services.email.send_email.transport.resolve_aws_credentials")
    @patch("authn.services.email.send_email.boto3")
    def test_returns_false_on_client_error(self, mock_boto3, mock_resolve):
        from botocore.exceptions import ClientError

        from core.services.aws.credentials import AwsCredentials

        mock_resolve.return_value = AwsCredentials(access_key_id="k", secret_access_key="s", region="us-west-2")
        mock_boto3.client.return_value.send_email.side_effect = ClientError(
            {"Error": {"Code": "MessageRejected", "Message": "boom"}}, "SendEmail"
        )
        config = _fake_config(ses_configured=True)
        result = _send_via_ses(config=config, recipient="a@b.com", subject="Hi", html_body="<p>Hi</p>")
        self.assertFalse(result)


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

    @patch("authn.services.email.send_email._send_via_ses", return_value=True)
    @patch("authn.services.email.send_email._load_config")
    def test_ses_success_completes(self, mock_config, mock_ses):
        mock_config.return_value = _fake_config(ses_configured=True)
        send_verification_email(recipient="a@b.com", code="123456", purpose="admin_login")
        mock_ses.assert_called_once()

    @patch("authn.services.email.send_email._send_via_ses", return_value=False)
    @patch("authn.services.email.send_email._load_config")
    def test_ses_failure_raises_without_smtp_fallback(self, mock_config, mock_ses):
        mock_config.return_value = _fake_config(ses_configured=True)
        with self.assertRaises(RuntimeError):
            send_verification_email(recipient="a@b.com", code="123456", purpose="admin_login")
        mock_ses.assert_called_once()

    @patch("authn.services.email.send_email._send_via_ses", return_value=False)
    @patch("authn.services.email.send_email._load_config")
    def test_ses_not_configured_raises_without_smtp_fallback(self, mock_config, mock_ses):
        mock_config.return_value = _fake_config(ses_configured=False)
        with self.assertRaises(RuntimeError):
            send_verification_email(recipient="a@b.com", code="123456", purpose="admin_login")
        mock_ses.assert_called_once()


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

    @patch("authn.services.email.send_email._send_via_ses", return_value=False)
    @patch("authn.services.email.send_email._load_config")
    def test_ses_failure_raises(self, mock_config, mock_ses):
        mock_config.return_value = _fake_config(ses_configured=False)
        invitation = self._invitation()

        with self.assertRaises(RuntimeError):
            send_admin_invitation_email(invitation=invitation)

        mock_ses.assert_called_once()

    @patch("authn.services.email.send_email._send_via_ses", return_value=True)
    @patch("authn.services.email.send_email._load_config")
    def test_ses_success_sends_invitation(self, mock_config, mock_ses):
        mock_config.return_value = _fake_config(ses_configured=True)

        send_admin_invitation_email(invitation=self._invitation())

        mock_ses.assert_called_once()
