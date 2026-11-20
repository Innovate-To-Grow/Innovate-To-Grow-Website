"""The acknowledgement of a new ticket: off by default; with sending and it on, queued for a person's new ticket whose
sender passed DMARC (or compauth); never for automated, backfilled or no-auto-response mail or the site's own
address; at most once per address a day and ``ACK_DAILY_CAP`` in all."""

from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.models import BackgroundJob
from apps.core.services.email.inbound import NO_AUTO_RESPONSE

from ....models import HelpdeskSettings, Ticket, TicketEvent, TicketMessage
from ....services.outbound import acknowledgement, jobs
from ... import corpus
from ...helpers import FakeReader, receive
from ...helpers.service import new_ticket, sending_settings

AUTHENTICATED = {"Authentication-Results": "mx.example; spf=pass; dkim=pass; dmarc=pass action=none"}


def acks():
    return TicketMessage.objects.filter(kind=TicketMessage.Kind.REPLY, automatic=True)


@override_settings(BACKGROUND_JOBS_ENABLED=True)
class AcknowledgementIngestTests(TestCase):
    def setUp(self):
        cache.clear()
        self.reader = FakeReader()

    def receive(self, raw=None, **values):
        with self.captureOnCommitCallbacks(execute=True):
            return receive(raw or corpus.message(headers=AUTHENTICATED), reader=self.reader, **values)

    def test_off_by_default_even_with_sending_on(self):
        settings = sending_settings()
        self.assertFalse(settings.send_acknowledgement)

        self.receive()

        self.assertFalse(acks().exists())
        self.assertFalse(BackgroundJob.objects.filter(kind=jobs.REPLY_JOB_KIND).exists())

    def test_never_in_shadow_mode(self):
        HelpdeskSettings.objects.create(send_acknowledgement=True)

        self.receive()

        self.assertFalse(acks().exists())

    def test_queued_for_a_persons_new_ticket(self):
        sending_settings(send_acknowledgement=True)

        ticket = self.receive()

        ack = acks().get()
        self.assertEqual(ack.ticket, ticket)
        self.assertEqual(
            (ack.from_name, ack.to_addresses, ack.delivery_status, ack.author),
            ("Innovate to Grow", ["pat@example.org"], TicketMessage.Delivery.QUEUED, None),
        )
        self.assertEqual(ack.subject, f"Re: Question about the showcase [{ticket.display_number}]")
        self.assertIn(f"opened ticket {ticket.display_number}", ack.body_text)
        self.assertNotIn("{", ack.body_text)
        self.assertNotIn("in the subject", ack.body_text)  # the email's footer says how to reply
        self.assertEqual(ticket.events.get(kind=TicketEvent.Kind.ACKNOWLEDGED).data, {"to": "pat@example.org"})
        job = BackgroundJob.objects.get(kind=jobs.REPLY_JOB_KIND)
        self.assertEqual(job.payload, {"message_id": str(ack.pk)})
        # An acknowledgement is not a response: the SLA clock still waits for staff.
        ticket.refresh_from_db()
        self.assertIsNone(ticket.first_responded_at)

    def test_the_text_is_filled_from_the_settings(self):
        sending_settings(send_acknowledgement=True, acknowledgement_text="Got it: {ticket} / {subject}")

        ticket = self.receive()

        self.assertEqual(acks().get().body_text, f"Got it: {ticket.display_number} / Question about the showcase")

    def test_never_for_a_reply_that_joins_a_ticket(self):
        sending_settings(send_acknowledgement=True)
        self.receive()

        self.receive(corpus.message(message_id="<r@x>", in_reply_to="<m1@mail.example.org>", headers=AUTHENTICATED))

        self.assertEqual(acks().count(), 1)

    def test_never_without_authentication(self):
        sending_settings(send_acknowledgement=True)
        for number, headers in enumerate(({}, {"Authentication-Results": "mx.example; spf=pass; dmarc=fail"})):
            with self.subTest(headers):
                self.receive(
                    corpus.message(message_id=f"<u{number}@x>", sender=f"u{number}@example.org", headers=headers)
                )
        self.assertFalse(acks().exists())

    def test_compauth_pass_is_enough(self):
        sending_settings(send_acknowledgement=True)

        self.receive(corpus.message(headers={"Authentication-Results": "mx.example; dmarc=none; compauth=pass"}))

        self.assertEqual(acks().count(), 1)

    def test_never_for_automated_or_backfilled_mail(self):
        sending_settings(send_acknowledgement=True)

        self.receive(corpus.out_of_office())
        self.receive(corpus.message(headers=AUTHENTICATED), received=timezone.now() - timedelta(days=3))

        self.assertFalse(acks().exists())

    @override_settings(BACKGROUND_JOBS_ENABLED=False)
    def test_never_while_jobs_are_off(self):
        sending_settings(send_acknowledgement=True)

        self.receive()

        self.assertFalse(acks().exists())


@override_settings(BACKGROUND_JOBS_ENABLED=True)
class AcknowledgementLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.settings = sending_settings(send_acknowledgement=True)

    def opened(self, address="pat@example.org", **message_values):
        ticket = new_ticket(requester_email=address)
        message_values.setdefault("auth_summary", {"dmarc": "pass"})
        message = TicketMessage.objects.create(
            ticket=ticket,
            kind=TicketMessage.Kind.CUSTOMER,
            from_address=address,
            occurred_at=timezone.now(),
            **message_values,
        )
        with self.captureOnCommitCallbacks(execute=True):
            return acknowledgement.queue_acknowledgement(ticket, message, self.settings)

    def test_one_per_address_a_day(self):
        first = self.opened()

        self.assertIsNotNone(first)
        self.assertIsNone(self.opened())
        self.assertIsNotNone(self.opened("kim@example.org"))
        TicketMessage.objects.filter(pk=first.pk).update(occurred_at=timezone.now() - timedelta(hours=25))
        self.assertIsNotNone(self.opened())

    def test_at_most_the_daily_cap_in_all(self):
        with patch.object(acknowledgement, "ACK_DAILY_CAP", 2):
            self.assertIsNotNone(self.opened("a@example.org"))
            self.assertIsNotNone(self.opened("b@example.org"))
            self.assertIsNone(self.opened("c@example.org"))
        self.assertEqual(acks().count(), 2)

    def test_never_for_a_message_that_asks_for_no_automatic_reply(self):
        self.assertIsNone(self.opened(signals=[NO_AUTO_RESPONSE]))

    def test_never_to_an_address_that_cannot_be_mailed_or_the_sites_own(self):
        self.assertIsNone(self.opened("Pat <pat@example.org>"))
        self.assertIsNone(self.opened("I2G@g.ucmerced.edu"))
        self.assertFalse(acks().exists())

    def test_never_on_automated_or_spam_tickets(self):
        for values in ({"automated": True, "status": Ticket.Status.CLOSED}, {"status": Ticket.Status.SPAM}):
            ticket = new_ticket(**values)
            message = TicketMessage.objects.create(
                ticket=ticket,
                kind=TicketMessage.Kind.CUSTOMER,
                from_address="pat@example.org",
                occurred_at=timezone.now(),
                auth_summary={"dmarc": "pass"},
            )
            with self.subTest(values):
                self.assertIsNone(acknowledgement.queue_acknowledgement(ticket, message, self.settings))

    def test_unsaved_settings_still_judge_every_limit(self):
        unsaved = HelpdeskSettings(shadow_mode=False, send_acknowledgement=True)
        ticket = new_ticket()
        message = TicketMessage.objects.create(
            ticket=ticket, kind=TicketMessage.Kind.CUSTOMER, occurred_at=timezone.now(), auth_summary={"dmarc": "PASS"}
        )

        with self.captureOnCommitCallbacks(execute=True):
            self.assertIsNotNone(acknowledgement.queue_acknowledgement(ticket, message, unsaved))
