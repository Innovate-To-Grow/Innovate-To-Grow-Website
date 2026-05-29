from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.event.models import EventRegistration, Ticket
from apps.event.services.ticket_mail import send_ticket_email
from apps.event.tests.helpers import make_event, make_member


def _mock_config(ses_configured=True):
    config = MagicMock()
    config.ses_configured = ses_configured
    config.source_address = "Innovate to Grow <i2g@test.com>"
    return config


def _aws_creds():
    from core.services.aws.credentials import AwsCredentials

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
