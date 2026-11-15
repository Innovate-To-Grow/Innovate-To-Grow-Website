import base64
import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from apps.core.services.aws.provider_outcomes import ProviderDeliveryError
from apps.core.services.background_jobs import TransientJobError
from apps.core.services.email import (
    TransientEmailDeliveryError,
)
from apps.core.tests.services.graph.provider.test_email_graph import GraphFixtureMixin, make_provider
from apps.event.models import EventRegistration, Ticket
from apps.event.services.ticket.jobs import send_ticket_email_job
from apps.event.services.ticket.mail import send_ticket_email
from apps.event.services.ticket.message import _build_ticket_message
from apps.event.tests.helpers import make_event, make_member
from apps.event.tests.services.tickets.mail.test_ticket_mail import _mock_config


class TicketJobRetryAfterTest(TestCase):
    def setUp(self):
        event = make_event()
        ticket = Ticket.objects.create(event=event, name="GA")
        self.registration = EventRegistration.objects.create(member=make_member(), event=event, ticket=ticket)

    @patch("apps.event.services.ticket.mail.deliver_email")
    @patch("apps.event.services.ticket.mail._load_config", return_value=_mock_config())
    def test_a_throttled_ticket_job_retries_no_sooner_than_the_provider_asked(self, _config, deliver):
        deliver.side_effect = TransientEmailDeliveryError("throttled", retry_after=120.0)
        job = MagicMock(payload={"registration_id": str(self.registration.pk)})

        with patch("apps.core.models.BackgroundJob.objects") as jobs:
            jobs.select_for_update.return_value.filter.return_value.exists.return_value = True
            with self.assertRaises(TransientJobError) as caught:
                send_ticket_email_job(job)

        self.assertEqual(caught.exception.retry_after, 120.0)

    @patch("apps.event.services.ticket.mail.deliver_email")
    @patch("apps.event.services.ticket.mail._load_config", return_value=_mock_config())
    def test_a_ticket_held_back_by_the_delivery_rate_reruns_at_its_slot(self, _config, deliver):
        from apps.core.services.background_jobs import DeferredJobError
        from apps.core.services.delivery_rates import RateDeferred
        from apps.core.services.email.exceptions import EmailRateDeferred

        now = timezone.now()
        deliver.side_effect = EmailRateDeferred(RateDeferred(now + timedelta(seconds=40), "cooldown", now=now))
        job = MagicMock(payload={"registration_id": str(self.registration.pk)})

        with patch("apps.core.models.BackgroundJob.objects") as jobs:
            jobs.select_for_update.return_value.filter.return_value.exists.return_value = True
            with self.assertRaises(DeferredJobError) as caught:
                send_ticket_email_job(job)

        self.assertEqual(caught.exception.until, now + timedelta(seconds=40))
        # Nothing was sent, so the provisional login link is gone again.
        self.assertFalse(self.registration.login_tokens.exists())

    @patch("apps.event.services.ticket.mail.deliver_email")
    @patch("apps.event.services.ticket.mail._load_config", return_value=_mock_config())
    def test_a_direct_send_still_reports_a_generic_failure(self, _config, deliver):
        deliver.side_effect = TransientEmailDeliveryError("throttled", retry_after=30.0)

        with self.assertRaises(RuntimeError) as caught:
            send_ticket_email(self.registration)

        self.assertNotIsInstance(caught.exception, ProviderDeliveryError)
        self.registration.refresh_from_db()
        self.assertNotEqual(self.registration.ticket_email_error, "")


class TicketThroughGraphTest(GraphFixtureMixin, TestCase):
    """Through Microsoft Graph the ticket goes as JSON sendMail: no Sent Items copy, barcode still inline."""

    def test_the_ticket_is_json_with_save_to_sent_items_false_and_its_attachments(self):
        event = make_event()
        registration = EventRegistration.objects.create(
            member=make_member(), event=event, ticket=Ticket.objects.create(event=event, name="GA")
        )
        message = _build_ticket_message(registration, config=_mock_config(), login_url="https://i2g.example/l#token=t")

        make_provider().send(message)

        request = self.fake.send_requests[0]
        self.assertEqual(request.headers["Content-Type"], "application/json")
        body = json.loads(request.body)
        self.assertIs(body["saveToSentItems"], False)
        sent = body["message"]
        self.assertIn("https://i2g.example/l#token=t", sent["body"]["content"])
        self.assertIn("cid:ticket-barcode", sent["body"]["content"])
        barcode, calendar = sent["attachments"]
        self.assertEqual(
            {key: barcode[key] for key in ("name", "contentType", "isInline", "contentId")},
            {"name": "ticket-barcode.png", "contentType": "image/png", "isInline": True, "contentId": "ticket-barcode"},
        )
        self.assertEqual(base64.b64decode(barcode["contentBytes"]), message.attachments[0].content)
        self.assertEqual((calendar["name"], calendar["contentType"]), ("event.ics", "text/calendar"))
        self.assertNotIn("isInline", calendar)
