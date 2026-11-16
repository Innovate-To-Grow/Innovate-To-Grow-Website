from unittest.mock import patch

from django.test import TestCase

from apps.authn.services.email.send_email import (
    _send_via_ses,
    send_admin_invitation_email,
    send_notification_email,
    send_verification_email,
)
from apps.authn.tests.services.email.delivery.test_send_email import SendAdminInvitationEmailTests, _fake_config


class SentItemsCopyTests(TestCase):
    """Mail that carries a credential asks the provider to keep no Sent Items copy (Graph honours it)."""

    @patch("apps.authn.services.email.send_email.transport.deliver_email")
    def test_the_flag_reaches_the_message_and_defaults_to_keeping_a_copy(self, mock_deliver):
        config = _fake_config(ses_configured=True)

        _send_via_ses(config=config, recipient="a@b.com", subject="Hi", html_body="<p>Hi</p>")
        _send_via_ses(config=config, recipient="a@b.com", subject="Hi", html_body="<p>Hi</p>", keep_sent_copy=False)

        flags = [call.args[0].keep_sent_copy for call in mock_deliver.call_args_list]
        self.assertEqual(flags, [True, False])

    @patch("apps.authn.services.email.send_email._send_via_ses", return_value=True)
    @patch("apps.authn.services.email.send_email._load_config")
    def test_every_verification_purpose_keeps_no_copy(self, mock_config, mock_ses):
        from apps.authn.services.email.send_email.config import PURPOSE_SUBJECTS

        mock_config.return_value = _fake_config(ses_configured=True)
        for purpose in PURPOSE_SUBJECTS:
            with self.subTest(purpose=purpose):
                send_verification_email(recipient="a@b.com", code="123456", purpose=purpose)
                self.assertIs(mock_ses.call_args.kwargs["keep_sent_copy"], False)

    @patch("apps.authn.services.email.send_email._send_via_ses", return_value=True)
    @patch("apps.authn.services.email.send_email._load_config")
    def test_admin_invitations_keep_no_copy(self, mock_config, mock_ses):
        mock_config.return_value = _fake_config(ses_configured=True)

        send_admin_invitation_email(invitation=SendAdminInvitationEmailTests()._invitation())

        self.assertIs(mock_ses.call_args.kwargs["keep_sent_copy"], False)

    @patch("apps.authn.services.email.send_email._send_via_ses", return_value=True)
    @patch("apps.authn.services.email.send_email._load_config")
    def test_notifications_without_credentials_keep_the_default(self, mock_config, mock_ses):
        mock_config.return_value = _fake_config(ses_configured=True)

        send_notification_email(
            recipient="owner@example.com",
            subject="Security notice",
            template="authn/email/email_claim_notification.html",
            context={"account_url": "https://example.com/account"},
        )

        self.assertNotIn("keep_sent_copy", mock_ses.call_args.kwargs)
