"""Replies to the requester: when they are refused (shadow mode, merged, automated or spam, an address that cannot be
mailed or is the site's own, jobs off, an empty or too long text, a bad Cc), and what a queued reply stores, records
and enqueues (the first response only once the job sent it); and which message a reply quotes."""

from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.models import BackgroundJob

from ....models import HelpdeskSettings, Ticket, TicketEvent, TicketMessage
from ....services import outbound
from ....services.outbound import jobs, replies
from ... import corpus
from ...helpers import helpdesk_staff
from ...helpers.service import Status, clocked_ticket, new_ticket, sending_settings
from .test_jobs import DELIVER, claimed, delivered

Kind = TicketEvent.Kind
Delivery = TicketMessage.Delivery


@override_settings(BACKGROUND_JOBS_ENABLED=True)
class QueueReplyTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()
        self.settings = sending_settings()
        self.ticket = clocked_ticket(participants=["pat@example.org"])

    def reply(self, ticket=None, **values):
        values.setdefault("body", "Hello Pat, the showcase starts at 10.")
        with self.captureOnCommitCallbacks(execute=True):
            return outbound.queue_reply(ticket or self.ticket, actor=self.agent, **values)

    def send(self, message):
        with patch(DELIVER, side_effect=delivered):
            jobs.send_reply_job(claimed(BackgroundJob.objects.get(dedupe_key=f"reply:{message.pk}")))

    def test_refused_while_shadow_mode_is_on(self):
        HelpdeskSettings.objects.update(shadow_mode=True)

        with self.assertRaisesMessage(outbound.ReplyRefused, "Shadow mode is on"):
            self.reply()
        self.assertFalse(TicketMessage.objects.filter(kind=TicketMessage.Kind.REPLY).exists())

    def test_refused_for_merged_automated_and_spam_tickets(self):
        for ticket in (
            new_ticket(status=Status.MERGED),
            new_ticket(automated=True, status=Status.CLOSED),
            new_ticket(status=Status.SPAM),
        ):
            with self.subTest(ticket.status), self.assertRaises(outbound.ReplyRefused):
                self.reply(ticket)

    @override_settings(BACKGROUND_JOBS_ENABLED=False)
    def test_refused_while_jobs_are_off(self):
        with self.assertRaisesMessage(outbound.ReplyRefused, "Background jobs are off"):
            self.reply()

    def test_refused_without_text_or_with_too_much(self):
        for body, reason in (
            ("", "Write the reply"),
            ("   \n ", "Write the reply"),
            ("\x00", "Write the reply"),
            ("Hello. " * 3000, "A reply can be at most 20,000 characters (20,999 written)."),
        ):
            with self.subTest(len(body)), self.assertRaisesMessage(outbound.ReplyRefused, reason):
                self.reply(body=body)
        self.assertFalse(BackgroundJob.objects.exists())

    def test_refused_with_a_bad_cc(self):
        with self.assertRaisesMessage(
            outbound.ReplyRefused,
            '"not an address" in Cc is not a plain email address (use name@example.com, separated by commas).',
        ):
            self.reply(cc="not an address")
        with self.assertRaisesMessage(
            outbound.ReplyRefused, "i2g@g.ucmerced.edu is the helpdesk's own address: it is never copied on a reply."
        ):
            self.reply(cc="kim@example.org, I2G@g.ucmerced.edu")
        self.assertFalse(TicketMessage.objects.filter(kind=TicketMessage.Kind.REPLY).exists())

    def test_a_reply_is_stored_queued_recorded_and_enqueued_when_it_commits(self):
        message = self.reply(body=f"  See {corpus.LOGIN_LINK}  ", cc="Kim@example.org, pat@example.org")

        message.refresh_from_db()
        self.assertEqual(
            (message.kind, message.author, message.from_name, message.delivery_status),
            (TicketMessage.Kind.REPLY, self.agent, "Avery Agent", Delivery.QUEUED),
        )
        self.assertEqual(message.from_address, "i2g@g.ucmerced.edu")
        self.assertEqual((message.to_addresses, message.cc_addresses), (["pat@example.org"], ["kim@example.org"]))
        self.assertEqual(message.subject, f"Re: Question [{self.ticket.display_number}]")
        self.assertEqual(message.body_text, "See [sign-in link removed]")
        self.assertFalse(message.automatic)
        reply_event = self.ticket.events.get(kind=Kind.REPLY)
        self.assertEqual(
            (reply_event.actor, reply_event.data), (self.agent, {"to": "pat@example.org", "cc": ["kim@example.org"]})
        )
        # Queued is no response yet: the job records it once the reply went out.
        self.assertFalse(self.ticket.events.filter(kind=Kind.RESPONDED).exists())
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.participants, ["pat@example.org", "kim@example.org"])
        self.assertIsNone(self.ticket.first_responded_at)
        self.assertEqual(self.ticket.last_activity_at, message.occurred_at)
        self.assertEqual(self.ticket.status, Status.NEW)  # no status given: kept
        job = BackgroundJob.objects.get(kind=jobs.REPLY_JOB_KIND)
        self.assertEqual((job.dedupe_key, job.payload), (f"reply:{message.pk}", {"message_id": str(message.pk)}))
        self.assertFalse(job.can_retry_after_claim)

    def test_job_insert_failure_rolls_back_the_reply_and_status_change(self):
        with patch.object(jobs, "enqueue_reply", side_effect=RuntimeError("queue unavailable")):
            with self.assertRaisesMessage(RuntimeError, "queue unavailable"):
                self.reply(status=Status.PENDING_CUSTOMER)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, Status.NEW)
        self.assertFalse(self.ticket.messages.filter(kind=TicketMessage.Kind.REPLY).exists())
        self.assertFalse(self.ticket.events.filter(kind=Kind.REPLY).exists())

    def test_a_status_chosen_with_the_reply_is_set_at_once_and_is_no_response_until_it_is_sent(self):
        message = self.reply(status=Status.PENDING_CUSTOMER)

        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, Status.PENDING_CUSTOMER)
        self.assertIsNotNone(self.ticket.sla_paused_at)
        self.assertIsNone(self.ticket.first_responded_at)  # leaving New with the reply is not the response
        self.assertFalse(self.ticket.events.filter(kind=Kind.RESPONDED).exists())
        self.assertEqual(self.ticket.events.get(kind=Kind.STATUS).actor, self.agent)

        self.send(message)

        responded = self.ticket.events.get(kind=Kind.RESPONDED)
        self.assertEqual((responded.actor, responded.data), (self.agent, {"by": "reply"}))

    def test_a_later_reply_is_not_another_first_response(self):
        first = self.reply()
        second = self.reply(body="One more thing.")
        self.send(first)
        self.send(second)

        self.assertEqual(self.ticket.events.filter(kind=Kind.RESPONDED).count(), 1)
        self.assertEqual(self.ticket.events.filter(kind=Kind.REPLY).count(), 2)
        self.assertEqual(BackgroundJob.objects.filter(kind=jobs.REPLY_JOB_KIND).count(), 2)
        first.refresh_from_db()
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.first_responded_at, first.delivered_at)

    def test_a_late_first_reply_breaches_the_response_when_it_is_sent(self):
        late = clocked_ticket(started=timezone.now() - timedelta(days=2))

        message = self.reply(late)
        late.refresh_from_db()
        self.assertFalse(late.response_breached)  # judged when it goes out, not when queued
        self.send(message)

        late.refresh_from_db()
        self.assertTrue(late.response_breached)
        self.assertEqual(late.events.get(kind=Kind.SLA_BREACHED).data, {"which": "response"})


class LastInboundTests(TestCase):
    def setUp(self):
        cache.clear()
        self.ticket = new_ticket(requester_email="Pat@Example.org")

    def message(self, minutes_ago, *, sender="pat@example.org", kind=TicketMessage.Kind.CUSTOMER):
        return TicketMessage.objects.create(
            ticket=self.ticket,
            kind=kind,
            from_address=sender,
            occurred_at=timezone.now() - timedelta(minutes=minutes_ago),
            body_text=f"{sender} {minutes_ago}",
        )

    def test_the_requesters_own_latest_message(self):
        self.message(30)
        latest = self.message(10, sender="PAT@example.org")
        self.message(5, sender="kim@example.org")  # a Cc'd participant: never quoted to the requester
        self.message(1, kind=TicketMessage.Kind.NOTE)
        self.message(1, kind=TicketMessage.Kind.AUTOMATED)

        self.assertEqual(replies.last_inbound(self.ticket), latest)

    def test_none_without_a_requester_or_their_message(self):
        self.message(5, sender="kim@example.org")

        self.assertIsNone(replies.last_inbound(self.ticket))
        Ticket.objects.filter(pk=self.ticket.pk).update(requester_email="")
        self.ticket.refresh_from_db()
        self.assertIsNone(replies.last_inbound(self.ticket))
