from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from apps.event.models import EventRegistration, Ticket
from apps.event.services.ticket_mail import TICKET_LOGIN_REDIRECT_PATH, _issue_ticket_login_link, send_ticket_email
from apps.event.tests.helpers import make_event, make_member
from apps.mail.models import LoginLinkToken


def _mock_config(ses_configured=True):
    config = MagicMock()
    config.ses_configured = ses_configured
    config.source_address = "Innovate to Grow <i2g@test.com>"
    return config


def _aws_creds():
    from apps.core.services.aws.credentials import AwsCredentials

    return AwsCredentials(access_key_id="test-key", secret_access_key="test-secret", region="us-west-2")


class SendTicketEmailTest(TestCase):
    def setUp(self):
        self.member = make_member()
        self.event = make_event(is_live=True)
        self.ticket = Ticket.objects.create(event=self.event, name="GA")
        self.registration = EventRegistration.objects.create(member=self.member, event=self.event, ticket=self.ticket)

    @patch("apps.event.services.ticket_mail.resolve_aws_credentials")
    @patch("apps.event.services.ticket_mail.boto3")
    @patch("apps.event.services.ticket_mail._load_config")
    def test_sends_via_ses(self, mock_load_config, mock_boto3, mock_resolve):
        mock_load_config.return_value = _mock_config(ses_configured=True)
        mock_resolve.return_value = _aws_creds()
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        send_ticket_email(self.registration)

        mock_client.send_raw_email.assert_called_once()
        raw_data = mock_client.send_raw_email.call_args[1]["RawMessage"]["Data"]
        self.assertIn("ticket-barcode", raw_data)
        self.assertIn(self.event.name, raw_data)
        self.assertIn("text/calendar", raw_data)
        self.assertIn("event.ics", raw_data)

        self.registration.refresh_from_db()
        self.assertIsNotNone(self.registration.ticket_email_sent_at)
        self.assertEqual(self.registration.ticket_email_error, "")

    @patch("apps.event.services.ticket_mail._send_via_ses", return_value=False)
    @patch("apps.event.services.ticket_mail._load_config")
    def test_records_error_when_ses_is_not_configured(self, mock_load_config, mock_ses):
        mock_load_config.return_value = _mock_config(ses_configured=False)

        with self.assertRaises(RuntimeError):
            send_ticket_email(self.registration)

        self.registration.refresh_from_db()
        self.assertIsNone(self.registration.ticket_email_sent_at)
        self.assertIn("AWS SES", self.registration.ticket_email_error)

    @patch("apps.event.services.ticket_mail._send_via_ses", return_value=False)
    @patch("apps.event.services.ticket_mail._load_config")
    def test_records_error_on_ses_failure(self, mock_load_config, mock_ses):
        mock_load_config.return_value = _mock_config(ses_configured=True)

        with self.assertRaises(RuntimeError):
            send_ticket_email(self.registration)

        self.registration.refresh_from_db()
        self.assertIsNone(self.registration.ticket_email_sent_at)
        self.assertIn("AWS SES", self.registration.ticket_email_error)

    @patch("apps.event.services.ticket_mail.resolve_aws_credentials")
    @patch("apps.event.services.ticket_mail.boto3")
    @patch("apps.event.services.ticket_mail._load_config")
    def test_sends_to_secondary_email(self, mock_load_config, mock_boto3, mock_resolve):
        mock_load_config.return_value = _mock_config(ses_configured=True)
        mock_resolve.return_value = _aws_creds()
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        self.registration.attendee_secondary_email = "secondary@example.com"
        self.registration.save(update_fields=["attendee_secondary_email"])

        send_ticket_email(self.registration)

        raw_data = mock_client.send_raw_email.call_args[1]["RawMessage"]["Data"]
        self.assertIn("secondary@example.com", raw_data)

    @patch("apps.event.services.ticket_mail.resolve_aws_credentials")
    @patch("apps.event.services.ticket_mail._load_config")
    def test_send_via_ses_returns_false_on_credentials_error(self, mock_load_config, mock_resolve):
        from apps.core.services.aws.credentials import AwsCredentialsError

        mock_load_config.return_value = _mock_config(ses_configured=True)
        mock_resolve.side_effect = AwsCredentialsError("missing creds")

        with self.assertRaises(RuntimeError):
            send_ticket_email(self.registration)

        self.registration.refresh_from_db()
        self.assertIsNone(self.registration.ticket_email_sent_at)
        self.assertIn("AWS SES", self.registration.ticket_email_error)

    @patch("apps.event.services.ticket_mail.resolve_aws_credentials")
    @patch("apps.event.services.ticket_mail.boto3")
    @patch("apps.event.services.ticket_mail._load_config")
    def test_send_via_ses_returns_false_on_client_error(self, mock_load_config, mock_boto3, mock_resolve):
        from botocore.exceptions import ClientError

        mock_load_config.return_value = _mock_config(ses_configured=True)
        mock_resolve.return_value = _aws_creds()
        mock_client = MagicMock()
        mock_client.send_raw_email.side_effect = ClientError(
            {"Error": {"Code": "MessageRejected", "Message": "rejected"}},
            "SendRawEmail",
        )
        mock_boto3.client.return_value = mock_client

        with self.assertRaises(RuntimeError):
            send_ticket_email(self.registration)

        self.registration.refresh_from_db()
        self.assertIsNone(self.registration.ticket_email_sent_at)
        self.assertIn("AWS SES", self.registration.ticket_email_error)

    @patch("apps.event.services.ticket_mail.resolve_aws_credentials")
    @patch("apps.event.services.ticket_mail.boto3")
    @patch("apps.event.services.ticket_mail._load_config")
    def test_clears_previous_error_on_success(self, mock_load_config, mock_boto3, mock_resolve):
        mock_load_config.return_value = _mock_config(ses_configured=True)
        mock_resolve.return_value = _aws_creds()
        mock_boto3.client.return_value = MagicMock()

        self.registration.ticket_email_error = "Previous failure"
        self.registration.save(update_fields=["ticket_email_error"])

        send_ticket_email(self.registration)

        self.registration.refresh_from_db()
        self.assertEqual(self.registration.ticket_email_error, "")
        self.assertIsNotNone(self.registration.ticket_email_sent_at)


class TicketLoginLinkIssuanceTest(TestCase):
    """Ticket emails issue unified LoginLinkToken rows scoped to the registration."""

    def setUp(self):
        self.member = make_member()
        self.event = make_event(is_live=True)
        self.ticket = Ticket.objects.create(event=self.event, name="GA")
        self.registration = EventRegistration.objects.create(member=self.member, event=self.event, ticket=self.ticket)

    def test_issues_token_bound_to_registration_with_ticket_redirect(self):
        url = _issue_ticket_login_link(self.registration)

        token = LoginLinkToken.objects.get(registration=self.registration)
        self.assertEqual(token.member_id, self.member.pk)
        self.assertIsNone(token.campaign)
        self.assertEqual(token.redirect_path, TICKET_LOGIN_REDIRECT_PATH)
        self.assertIn(f"/login-link?token={token.token}", url)

    def test_validity_comes_from_event_config(self):
        self.event.ticket_login_validity_days = 5
        self.event.save(update_fields=["ticket_login_validity_days", "updated_at"])

        before = timezone.now() + timedelta(days=5)
        _issue_ticket_login_link(self.registration)
        after = timezone.now() + timedelta(days=5)

        token = LoginLinkToken.objects.get(registration=self.registration)
        self.assertGreaterEqual(token.expires_at, before)
        self.assertLessEqual(token.expires_at, after)

    def test_reissue_revokes_previous_token(self):
        _issue_ticket_login_link(self.registration)
        first = LoginLinkToken.objects.get(registration=self.registration)

        _issue_ticket_login_link(self.registration)

        first.refresh_from_db()
        self.assertTrue(first.is_expired)
        active = self.registration.login_tokens.filter(expires_at__gt=timezone.now())
        self.assertEqual(active.count(), 1)

    def test_returns_empty_string_without_member(self):
        unsaved = EventRegistration(member=None, event=self.event, ticket=self.ticket)
        self.assertEqual(_issue_ticket_login_link(unsaved), "")

    @patch("apps.event.services.ticket_mail.resolve_aws_credentials")
    @patch("apps.event.services.ticket_mail.boto3")
    @patch("apps.event.services.ticket_mail._load_config")
    def test_send_ticket_email_embeds_login_link(self, mock_load_config, mock_boto3, mock_resolve):
        mock_load_config.return_value = _mock_config(ses_configured=True)
        mock_resolve.return_value = _aws_creds()
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        send_ticket_email(self.registration)

        token = LoginLinkToken.objects.get(registration=self.registration)
        raw_data = mock_client.send_raw_email.call_args[1]["RawMessage"]["Data"]
        # The HTML body is a base64 MIME part — decode it before matching.
        import email as email_lib

        message = email_lib.message_from_string(raw_data)
        html = next(
            part.get_payload(decode=True).decode() for part in message.walk() if part.get_content_type() == "text/html"
        )
        self.assertIn(f"/login-link?token={token.token}", html)

    def test_registration_delete_cascades_tokens(self):
        _issue_ticket_login_link(self.registration)
        self.assertEqual(LoginLinkToken.objects.filter(registration=self.registration).count(), 1)

        registration_id = self.registration.pk
        self.registration.delete()
        self.assertEqual(LoginLinkToken.objects.filter(registration_id=registration_id).count(), 0)
