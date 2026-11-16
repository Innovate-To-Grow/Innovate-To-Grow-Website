from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.core.services.email import (
    DeliveryResult,
)
from apps.event.models import EventRegistration, Ticket
from apps.event.services.ticket.mail import send_ticket_email
from apps.event.services.ticket.message import _build_mime_message, _issue_ticket_login_link
from apps.event.tests.helpers import make_event, make_member
from apps.mail.models import LoginLinkToken


def _mock_config(ses_configured=True):
    config = MagicMock()
    config.delivery_configured = ses_configured
    config.source_address = "Innovate to Grow <i2g@test.com>"
    return config


class _SendTicketEmailCase(TestCase):
    def setUp(self):
        self.member = make_member()
        self.event = make_event()
        self.ticket = Ticket.objects.create(event=self.event, name="GA")
        self.registration = EventRegistration.objects.create(member=self.member, event=self.event, ticket=self.ticket)


class SendTicketEmailTest(_SendTicketEmailCase):
    def test_builds_provider_neutral_pdf417_and_ics_attachments(self):
        message = _build_mime_message(
            subject="Ticket",
            from_address="ignored@example.com",
            recipients=["primary@example.com", "secondary@example.com"],
            html_body='<img src="cid:ticket-barcode">',
            barcode_bytes=b"png-data",
            ics_data="BEGIN:VCALENDAR",
        )
        self.assertEqual(message.to, ("primary@example.com", "secondary@example.com"))
        self.assertEqual(message.attachments[0].content_type, "image/png")
        self.assertEqual(message.attachments[0].filename, "ticket-barcode.png")
        self.assertEqual(message.attachments[1].content_type, "text/calendar")
        self.assertEqual(message.attachments[1].filename, "event.ics")
        self.assertIn("cid:ticket-barcode", message.html_body)
        # The ticket code and the login link are credentials: no copy may stay in the sender's Sent Items.
        self.assertIs(message.keep_sent_copy, False)

    @patch("apps.event.services.ticket.mail.deliver_email")
    @patch("apps.event.services.ticket.mail._load_config")
    def test_sends_via_ses(self, mock_load_config, mock_deliver):
        mock_load_config.return_value = _mock_config(ses_configured=True)
        mock_deliver.return_value = DeliveryResult(provider="ses", message_id="ticket-1")

        send_ticket_email(self.registration)

        mock_deliver.assert_called_once()
        message = mock_deliver.call_args.args[0]
        self.assertEqual(message.attachments[0].content_id, "ticket-barcode")
        self.assertEqual(message.attachments[0].disposition, "inline")
        self.assertEqual(message.attachments[1].content_type, "text/calendar")
        self.assertIn(self.event.name, message.html_body)

        self.registration.refresh_from_db()
        self.assertIsNotNone(self.registration.ticket_email_sent_at)
        self.assertEqual(self.registration.ticket_email_error, "")

    @patch("apps.event.services.ticket.mail._send_via_ses", return_value=False)
    @patch("apps.event.services.ticket.mail._load_config")
    def test_records_error_when_ses_is_not_configured(self, mock_load_config, mock_ses):
        mock_load_config.return_value = _mock_config(ses_configured=False)

        with self.assertRaises(RuntimeError):
            send_ticket_email(self.registration)

        self.registration.refresh_from_db()
        self.assertIsNone(self.registration.ticket_email_sent_at)
        self.assertIn("delivery provider", self.registration.ticket_email_error)

    @patch("apps.event.services.ticket.mail._send_via_ses")
    @patch("apps.event.services.ticket.mail._load_config")
    def test_unconfigured_resend_keeps_previous_login_link(self, mock_load_config, mock_ses):
        mock_load_config.return_value = _mock_config(ses_configured=False)
        _issue_ticket_login_link(self.registration)
        previous = LoginLinkToken.objects.get(registration=self.registration)

        with self.assertRaises(RuntimeError):
            send_ticket_email(self.registration)

        previous.refresh_from_db()
        self.assertTrue(previous.is_valid)
        self.assertEqual(self.registration.login_tokens.count(), 1)
        mock_ses.assert_not_called()

    @patch("apps.event.services.ticket.mail._send_via_ses", return_value=False)
    @patch("apps.event.services.ticket.mail._load_config")
    def test_records_error_on_ses_failure(self, mock_load_config, mock_ses):
        mock_load_config.return_value = _mock_config(ses_configured=True)

        with self.assertRaises(RuntimeError):
            send_ticket_email(self.registration)

        self.registration.refresh_from_db()
        self.assertIsNone(self.registration.ticket_email_sent_at)
        self.assertIn("delivery provider", self.registration.ticket_email_error)

    @patch("apps.event.services.ticket.mail._send_via_ses", return_value=False)
    @patch("apps.event.services.ticket.mail._load_config")
    def test_failed_resend_keeps_previous_login_link(self, mock_load_config, _mock_ses):
        mock_load_config.return_value = _mock_config(ses_configured=True)
        _issue_ticket_login_link(self.registration)
        previous = LoginLinkToken.objects.get(registration=self.registration)

        with self.assertRaises(RuntimeError):
            send_ticket_email(self.registration)

        previous.refresh_from_db()
        self.assertTrue(previous.is_valid)
        self.assertEqual(
            list(self.registration.login_tokens.values_list("pk", flat=True)),
            [previous.pk],
        )

    @patch("apps.event.services.ticket.mail._send_via_ses")
    @patch("apps.event.services.ticket.mail._load_config")
    def test_lost_claim_before_token_mutation_keeps_previous_link(self, mock_load_config, mock_ses):
        from apps.core.services.background_jobs import JobClaimLost

        mock_load_config.return_value = _mock_config(ses_configured=True)
        _issue_ticket_login_link(self.registration)
        previous = LoginLinkToken.objects.get(registration=self.registration)

        with self.assertRaises(JobClaimLost):
            send_ticket_email(
                self.registration,
                before_token_mutation=MagicMock(side_effect=JobClaimLost("claim replaced")),
            )

        previous.refresh_from_db()
        self.registration.refresh_from_db()
        self.assertTrue(previous.is_valid)
        self.assertEqual(self.registration.login_tokens.count(), 1)
        self.assertEqual(self.registration.ticket_email_error, "")
        mock_ses.assert_not_called()
