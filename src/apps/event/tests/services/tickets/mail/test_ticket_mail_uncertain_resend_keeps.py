import datetime
from unittest.mock import patch

from django.utils import timezone

from apps.core.services.email import (
    DeliveryResult,
    UncertainEmailDeliveryError,
)
from apps.event.services.ticket.mail import send_ticket_email
from apps.event.services.ticket.message import _issue_ticket_login_link
from apps.event.tests.services.tickets.mail.test_ticket_mail import _mock_config, _SendTicketEmailCase
from apps.mail.models import LoginLinkToken


class SendTicketEmailTest(_SendTicketEmailCase):
    @patch("apps.event.services.ticket.mail.deliver_email")
    @patch("apps.event.services.ticket.mail._load_config")
    def test_uncertain_resend_keeps_previous_and_provisional_links(
        self,
        mock_load_config,
        mock_deliver,
    ):
        mock_load_config.return_value = _mock_config(ses_configured=True)

        def lose_response(*args, **kwargs):
            kwargs["before_provider_call"]()
            raise UncertainEmailDeliveryError("response lost")

        mock_deliver.side_effect = lose_response
        _issue_ticket_login_link(self.registration)
        previous = LoginLinkToken.objects.get(registration=self.registration)

        with self.assertRaises(RuntimeError):
            send_ticket_email(self.registration)

        previous.refresh_from_db()
        self.assertTrue(previous.is_valid)
        self.assertEqual(
            self.registration.login_tokens.filter(expires_at__gt=timezone.now()).count(),
            2,
        )

    @patch("apps.event.services.ticket.mail.deliver_email")
    @patch("apps.event.services.ticket.mail._load_config")
    def test_clears_previous_error_on_success(self, mock_load_config, mock_deliver):
        mock_load_config.return_value = _mock_config(ses_configured=True)
        mock_deliver.return_value = DeliveryResult(provider="ses", message_id="ticket-1")

        self.registration.ticket_email_error = "Previous failure"
        self.registration.save(update_fields=["ticket_email_error"])

        send_ticket_email(self.registration)

        self.registration.refresh_from_db()
        self.assertEqual(self.registration.ticket_email_error, "")
        self.assertIsNotNone(self.registration.ticket_email_sent_at)

    @patch("apps.event.services.ticket.mail.deliver_email")
    @patch("apps.event.services.ticket.mail._load_config")
    def test_cross_year_range_is_in_email_and_calendar_links(self, mock_load_config, mock_deliver):
        mock_load_config.return_value = _mock_config(ses_configured=True)
        self.event.date = datetime.date(2026, 12, 31)
        self.event.end_date = datetime.date(2027, 1, 2)
        self.event.save(update_fields=["date", "end_date", "updated_at"])

        send_ticket_email(self.registration)

        message = mock_deliver.call_args.args[0]
        html = message.html_body
        calendar = message.attachments[1].content.decode()
        self.assertIn("December 31, 2026–January 2, 2027", html)
        self.assertIn("dates=20261231%2F20270103", html)
        self.assertIn("DTSTART;VALUE=DATE:20261231", calendar)
        self.assertIn("DTEND;VALUE=DATE:20270103", calendar)
