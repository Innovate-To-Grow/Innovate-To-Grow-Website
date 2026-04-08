from unittest.mock import MagicMock, patch

from django.test import TestCase

from event.models import EventRegistration, Ticket
from event.services.ticket_mail import send_ticket_email
from event.tests.helpers import make_event, make_member


def _mock_config(ses_configured=True):
    config = MagicMock()
    config.ses_configured = ses_configured
    config.ses_region = "us-west-2"
    config.ses_access_key_id = "test-key"
    config.ses_secret_access_key = "test-secret"
    config.source_address = "Innovate to Grow <i2g@test.com>"
    config.smtp_host = "smtp.test.com"
    config.smtp_port = 587
    config.smtp_username = "user"
    config.smtp_password = "pass"
    config.smtp_use_tls = True
    return config


class SendTicketEmailTest(TestCase):
    def setUp(self):
        self.member = make_member()
        self.event = make_event(is_live=True)
        self.ticket = Ticket.objects.create(event=self.event, name="GA")
        self.registration = EventRegistration.objects.create(member=self.member, event=self.event, ticket=self.ticket)

    @patch("event.services.ticket_mail.boto3")
    @patch("event.services.ticket_mail._load_config")
    def test_sends_via_ses(self, mock_load_config, mock_boto3):
        mock_load_config.return_value = _mock_config(ses_configured=True)
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

    @patch("event.services.ticket_mail._send_via_smtp")
    @patch("event.services.ticket_mail._send_via_ses", return_value=False)
    @patch("event.services.ticket_mail._load_config")
    def test_falls_back_to_smtp(self, mock_load_config, mock_ses, mock_smtp):
        mock_load_config.return_value = _mock_config(ses_configured=False)

        send_ticket_email(self.registration)

        mock_smtp.assert_called_once()
        self.registration.refresh_from_db()
        self.assertIsNotNone(self.registration.ticket_email_sent_at)

    @patch("event.services.ticket_mail._send_via_smtp", side_effect=ConnectionError("SMTP down"))
    @patch("event.services.ticket_mail._send_via_ses", return_value=False)
    @patch("event.services.ticket_mail._load_config")
    def test_records_error_on_failure(self, mock_load_config, mock_ses, mock_smtp):
        mock_load_config.return_value = _mock_config(ses_configured=False)

        with self.assertRaises(ConnectionError):
            send_ticket_email(self.registration)

        self.registration.refresh_from_db()
        self.assertIsNone(self.registration.ticket_email_sent_at)
        self.assertIn("SMTP down", self.registration.ticket_email_error)

    @patch("event.services.ticket_mail.boto3")
    @patch("event.services.ticket_mail._load_config")
    def test_sends_to_secondary_email(self, mock_load_config, mock_boto3):
        mock_load_config.return_value = _mock_config(ses_configured=True)
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        self.registration.attendee_secondary_email = "secondary@example.com"
        self.registration.save(update_fields=["attendee_secondary_email"])

        send_ticket_email(self.registration)

        raw_data = mock_client.send_raw_email.call_args[1]["RawMessage"]["Data"]
        self.assertIn("secondary@example.com", raw_data)

    @patch("event.services.ticket_mail.boto3")
    @patch("event.services.ticket_mail._load_config")
    def test_clears_previous_error_on_success(self, mock_load_config, mock_boto3):
        mock_load_config.return_value = _mock_config(ses_configured=True)
        mock_boto3.client.return_value = MagicMock()

        self.registration.ticket_email_error = "Previous failure"
        self.registration.save(update_fields=["ticket_email_error"])

        send_ticket_email(self.registration)

        self.registration.refresh_from_db()
        self.assertEqual(self.registration.ticket_email_error, "")
        self.assertIsNotNone(self.registration.ticket_email_sent_at)
