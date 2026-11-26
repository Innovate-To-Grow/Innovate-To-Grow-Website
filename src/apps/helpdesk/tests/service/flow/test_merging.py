"""A merge and what was still to happen on the merged tickets: a reply or acknowledgement still queued on a merged
ticket is marked failed, with the reason on the target's timeline, and the send job never sends it; the target is
unread when a person's merged ticket was (automated mail does not count); a resolved or closed target is reopened
when a person's open ticket is merged into it (its resolution cleared, its clock running again), and stays as it is
when the merged ticket was done too."""

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.models import BackgroundJob

from ....models import TicketEvent, TicketMessage
from ....services import outbound, tickets
from ....services.tickets import events
from ...helpers import helpdesk_staff
from ...helpers.service import Status, clocked_ticket, new_ticket
from ..outbound.test_jobs import JobTestCase, claimed

Kind = TicketEvent.Kind
Delivery = TicketMessage.Delivery


class QueuedRepliesOfAMergedTicketTests(JobTestCase):
    def setUp(self):
        super().setUp()
        self.newer = new_ticket(subject="Judging, again", participants=["pat@example.org"])  # merged into the oldest

    def test_they_are_failed_with_the_reason_on_the_target_and_never_sent(self):
        with self.captureOnCommitCallbacks(execute=True):
            reply = outbound.queue_reply(self.newer, actor=self.agent, body="Yes, please register.")
        job = claimed(BackgroundJob.objects.get(dedupe_key=f"reply:{reply.pk}"))
        ack = TicketMessage.objects.create(
            ticket=self.newer,
            kind=TicketMessage.Kind.REPLY,
            automatic=True,
            to_addresses=["pat@example.org"],
            occurred_at=timezone.now(),
            body_text="We have your message.",
            delivery_status=Delivery.QUEUED,
        )
        sent = TicketMessage.objects.create(
            ticket=self.newer,
            kind=TicketMessage.Kind.REPLY,
            to_addresses=["pat@example.org"],
            occurred_at=timezone.now(),
            body_text="Sent before the merge.",
            delivery_status=Delivery.SENT,
        )

        tickets.merge([self.newer, self.ticket], actor=self.agent)

        error = (
            f"Not sent: {self.newer.display_number} was merged into {self.ticket.display_number} before it went out. "
            "Write the reply again here if it is still needed."
        )
        for message in (reply, ack):
            message.refresh_from_db()
            self.assertEqual(
                (message.ticket_id, message.delivery_status, message.delivery_error),
                (self.ticket.pk, Delivery.FAILED, error),
            )
        sent.refresh_from_db()
        self.assertEqual(sent.delivery_status, Delivery.SENT)
        failed = list(self.ticket.events.filter(kind=Kind.REPLY_FAILED))
        self.assertEqual(sorted(event.data["what"] for event in failed), ["acknowledgement", "reply"])
        self.assertEqual({event.data["error"] for event in failed}, {error})
        self.assertFalse(self.newer.events.filter(kind=Kind.REPLY_FAILED).exists())
        reply_failed = next(event for event in failed if event.data["what"] == "reply")
        self.assertEqual(
            events.describe(reply_failed),
            f"The reply was not sent: {self.newer.display_number} was merged into {self.ticket.display_number} "
            "before it went out. Write the reply again here if it is still needed.",
        )

        self.run_job(job).assert_not_called()  # the job sends only replies still queued

        reply.refresh_from_db()
        self.assertEqual(reply.delivery_status, Delivery.FAILED)
        self.assertEqual(self.ticket.events.filter(kind=Kind.REPLY_FAILED).count(), 2)


class MergeTargetTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()

    def test_the_target_is_unread_when_a_persons_merged_ticket_was(self):
        target = new_ticket(unread=False)
        source = new_ticket(unread=True)

        tickets.merge([target, source], actor=self.agent)

        target.refresh_from_db()
        self.assertTrue(target.unread)

    def test_unread_automated_mail_does_not_make_the_target_unread(self):
        target = new_ticket(unread=False)
        automated = new_ticket(automated=True, status=Status.CLOSED, classification="auto_reply", unread=True)

        tickets.merge([target, automated], actor=self.agent)

        target.refresh_from_db()
        self.assertFalse(target.unread)

    def test_a_resolved_target_is_reopened_when_a_persons_open_ticket_is_merged_into_it(self):
        target = clocked_ticket(status=Status.OPEN)
        tickets.update_ticket(
            target, actor=self.agent, status=Status.RESOLVED, resolution_code="solved", resolution_notes="Sent it."
        )
        source = new_ticket()  # New: still open

        tickets.merge([source, target], actor=self.agent)

        target.refresh_from_db()
        self.assertEqual(
            (target.status, target.resolution_code, target.resolution_notes, target.closed_at, target.resolved_at),
            (Status.OPEN, "", "", None, None),
        )
        self.assertIsNone(target.sla_paused_at)  # its resolution clock runs again
        statuses = list(target.events.filter(kind=Kind.STATUS).values_list("actor", "data"))
        reopened = {"from": "resolved", "to": "open", "reason": "an open ticket was merged into it"}
        self.assertIn((self.agent.pk, reopened), statuses)
        self.assertIn(
            {"cleared": "solved"}, list(target.events.filter(kind=Kind.RESOLUTION).values_list("data", flat=True))
        )

    def test_a_closed_target_stays_closed_when_the_merged_ticket_was_done_too(self):
        now = timezone.now()
        target = new_ticket(status=Status.CLOSED, closed_at=now, resolution_code="solved")
        source = new_ticket(status=Status.RESOLVED, closed_at=now, resolved_at=now, resolution_code="duplicate")

        tickets.merge([target, source], actor=self.agent)

        target.refresh_from_db()
        self.assertEqual((target.status, target.resolution_code), (Status.CLOSED, "solved"))
        self.assertFalse(target.events.filter(kind__in=(Kind.STATUS, Kind.RESOLUTION)).exists())
