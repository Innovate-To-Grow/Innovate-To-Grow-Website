from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.authn.services.email.send_email import (
    _render_email_body,
    send_notification_email,
    send_verification_email,
)
from apps.authn.tests.services.email.delivery.test_send_email import _fake_config


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
        self.assertIn("email-auth-link#flow=register", html)
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
        self.assertIn("email-auth-link#flow=auth", html)
        self.assertIn("source=login", html)
        self.assertIn("email=member%40example.com", html)

    @override_settings(FRONTEND_URL="https://www.example.com")
    def test_render_body_includes_event_param_for_event_registration(self):
        html = _render_email_body(
            recipient="member@example.com",
            code="123456",
            purpose="login",
            link_flow="auth",
            link_source="event_registration",
            link_event="fall-showcase",
        )

        self.assertIn("Continue to Event Registration", html)
        self.assertIn("event=fall-showcase", html)

    @override_settings(FRONTEND_URL="https://www.example.com")
    def test_render_body_omits_event_param_when_no_event(self):
        html = _render_email_body(
            recipient="member@example.com",
            code="123456",
            purpose="login",
            link_flow="auth",
            link_source="event_registration",
            link_event="",
        )

        self.assertIn("email-auth-link#flow=auth", html)
        self.assertNotIn("event=", html)

    @override_settings(FRONTEND_URL="https://www.example.com")
    def test_render_body_omits_public_link_for_admin_login(self):
        html = _render_email_body(
            recipient="admin@example.com",
            code="123456",
            purpose="admin_login",
        )

        self.assertNotIn("email-auth-link", html)
        self.assertNotIn("Continue Registration", html)
        self.assertNotIn("Sign In to Your Account", html)

    @patch("apps.authn.services.email.send_email._send_via_ses", return_value=True)
    @patch("apps.authn.services.email.send_email._load_config")
    def test_ses_success_completes(self, mock_config, mock_ses):
        mock_config.return_value = _fake_config(ses_configured=True)
        send_verification_email(recipient="a@b.com", code="123456", purpose="admin_login")
        mock_ses.assert_called_once()

    @patch("apps.authn.services.email.send_email._send_via_ses", return_value=False)
    @patch("apps.authn.services.email.send_email._load_config")
    def test_ses_failure_raises_without_smtp_fallback(self, mock_config, mock_ses):
        mock_config.return_value = _fake_config(ses_configured=True)
        with self.assertRaises(RuntimeError):
            send_verification_email(recipient="a@b.com", code="123456", purpose="admin_login")
        mock_ses.assert_called_once()

    @patch("apps.authn.services.email.send_email._send_via_ses", return_value=False)
    @patch("apps.authn.services.email.send_email._load_config")
    def test_ses_not_configured_raises_without_smtp_fallback(self, mock_config, mock_ses):
        mock_config.return_value = _fake_config(ses_configured=False)
        with self.assertRaises(RuntimeError):
            send_verification_email(recipient="a@b.com", code="123456", purpose="admin_login")
        mock_ses.assert_called_once()


class SendNotificationEmailTests(TestCase):
    @patch("apps.authn.services.email.send_email._send_via_ses", return_value=True)
    @patch("apps.authn.services.email.send_email._load_config")
    def test_notification_sent_via_ses(self, mock_config, mock_ses):
        mock_config.return_value = _fake_config(ses_configured=True)
        send_notification_email(
            recipient="owner@example.com",
            subject="Security notice",
            template="authn/email/email_claim_notification.html",
            context={"account_url": "https://example.com/account"},
        )
        mock_ses.assert_called_once()

    @patch("apps.authn.services.email.send_email._send_via_ses", return_value=False)
    @patch("apps.authn.services.email.send_email._load_config")
    def test_notification_logs_when_send_fails(self, mock_config, mock_ses):
        mock_config.return_value = _fake_config(ses_configured=False)
        # Should NOT raise — notification failures are swallowed (logged).
        send_notification_email(
            recipient="owner@example.com",
            subject="Security notice",
            template="authn/email/email_claim_notification.html",
            context={"account_url": ""},
        )
        mock_ses.assert_called_once()
