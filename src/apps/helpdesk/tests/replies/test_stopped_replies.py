"""A reply that never reached the requester, after the second live check of the admin:

- a closing reply (the ticket resolved or closed with it, or since) that fails, or that the mail service does not
  confirm, reopens the ticket: In progress with the reason, its resolution cleared and unread, so the request is
  neither done nor left to close automatically; an acknowledgement that fails leaves a resolved ticket as it is;
- a merge stops a staff reply still queued on a merged ticket after the merge on the target's timeline, and the
  target is unread (someone must write the reply again there); a stopped acknowledgement alone leaves it read;
- the merge's confirmation page names each ticket whose staff reply will not be sent."""

from django.test import override_settings
from django.utils import timezone

from apps.core.models import BackgroundJob

from ...models import Ticket, TicketEvent, TicketMessage
from ...services import outbound, tickets
from ...services.outbound import jobs
from ..helpers.service import Status, new_ticket
from ..service.flow.test_undelivered import finish
from ..service.outbound.test_jobs import JobTestCase, claimed
from ..service.queue.support import ACTION_SESSION_KEY, QueueCase

Kind = TicketEvent.Kind
Delivery = TicketMessage.Delivery


def queued(ticket, *, automatic) -> TicketMessage:
    """A reply (or, ``automatic``, an acknowledgement) still waiting to be sent on ``ticket``."""
    return TicketMessage.objects.create(
        ticket=ticket,
        kind=TicketMessage.Kind.REPLY,
        automatic=automatic,
        to_addresses=["pat@example.org"],
        occurred_at=timezone.now(),
        body_text="We have your message." if automatic else "Yes, please register.",
        delivery_status=Delivery.QUEUED,
    )


class ClosingReplyTests(JobTestCase):
    def done_after_a_reply(self, status):
        """A reply queued, then the ticket resolved (and closed, for ``CLOSED``), and read since."""
        _message, job = self.queue()
        tickets.resolve([self.ticket], actor=self.agent, code="solved", notes="Registered.")
        if status == Status.CLOSED:
            self.ticket.refresh_from_db()
            tickets.close([self.ticket], actor=self.agent)
        Ticket.objects.filter(pk=self.ticket.pk).update(unread=False)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, status)
        return job

    def assert_reopened(self, done, reason):
        self.ticket.refresh_from_db()
        self.assertEqual((self.ticket.status, self.ticket.unread), (Status.OPEN, True))
        self.assertEqual((self.ticket.resolution_code, self.ticket.resolution_notes), ("", ""))
        self.assertEqual((self.ticket.resolved_at, self.ticket.closed_at), (None, None))  # nothing closes it later
        back = [event for event in self.ticket.events.filter(kind=Kind.STATUS) if event.data["from"] == done]
        self.assertEqual(len(back), 1)
        self.assertEqual((back[0].actor, back[0].data["to"], back[0].data["reason"]), (None, Status.OPEN, reason))

    def test_a_failed_closing_reply_reopens_a_resolved_ticket(self):
        finish(self.done_after_a_reply(Status.RESOLVED), BackgroundJob.Status.FAILED)

        self.assert_reopened(Status.RESOLVED, "the reply did not go out")

    def test_a_closing_reply_not_confirmed_reopens_a_closed_ticket(self):
        finish(self.done_after_a_reply(Status.CLOSED), BackgroundJob.Status.UNCERTAIN)

        self.assert_reopened(Status.CLOSED, "delivery not confirmed")

    def test_a_failed_acknowledgement_leaves_a_resolved_ticket_as_it_is(self):
        tickets.resolve([self.ticket], actor=self.agent, code="solved")
        Ticket.objects.filter(pk=self.ticket.pk).update(unread=False)

        finish(claimed(jobs.enqueue_reply(queued(self.ticket, automatic=True))), BackgroundJob.Status.FAILED)

        self.ticket.refresh_from_db()
        self.assertEqual(
            (self.ticket.status, self.ticket.unread, self.ticket.resolution_code), (Status.RESOLVED, False, "solved")
        )
        self.assertEqual(self.ticket.events.filter(kind=Kind.REPLY_FAILED).count(), 1)


class MergeStopsQueuedRepliesTests(JobTestCase):
    def setUp(self):
        super().setUp()
        self.newer = new_ticket(subject="Judging, again", participants=["pat@example.org"])  # merged into the oldest

    def merge_read_tickets(self):
        Ticket.objects.filter(pk__in=[self.ticket.pk, self.newer.pk]).update(unread=False)
        tickets.merge([self.newer, self.ticket], actor=self.agent)
        self.ticket.refresh_from_db()

    def test_a_stopped_staff_reply_follows_the_merge_and_leaves_the_target_unread(self):
        with self.captureOnCommitCallbacks(execute=True):
            outbound.queue_reply(self.newer, actor=self.agent, body="Yes, please register.")

        self.merge_read_tickets()

        self.assertTrue(self.ticket.unread)
        merged = self.ticket.events.get(kind=Kind.MERGED)
        stopped = self.ticket.events.get(kind=Kind.REPLY_FAILED)
        self.assertLess(merged.created_at, stopped.created_at)

    def test_a_stopped_acknowledgement_alone_leaves_the_target_read(self):
        queued(self.newer, automatic=True)

        self.merge_read_tickets()

        self.assertFalse(self.ticket.unread)
        self.assertEqual(self.ticket.events.get(kind=Kind.REPLY_FAILED).data["what"], "acknowledgement")


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class MergeConfirmationNoteTests(QueueCase):
    def test_the_note_names_each_ticket_whose_staff_reply_will_not_be_sent(self):
        oldest, waiting, acknowledged = new_ticket(), new_ticket(), new_ticket()
        queued(waiting, automatic=False)
        queued(acknowledged, automatic=True)

        notes = self.messages(self.act("merge_tickets", oldest, waiting, acknowledged))

        numbers = ", ".join(ticket.display_number for ticket in (oldest, waiting, acknowledged))
        self.assertEqual(
            notes,
            [
                f"Merging {numbers} into {oldest.display_number} (the oldest). A reply queued on "
                f"{waiting.display_number} will not be sent: write it again there."
            ],
        )
        self.assertIn(ACTION_SESSION_KEY, self.client.session)

    def test_without_a_queued_staff_reply_the_note_names_only_the_tickets(self):
        oldest, newer = new_ticket(), new_ticket()
        queued(newer, automatic=True)

        notes = self.messages(self.act("merge_tickets", oldest, newer))

        self.assertEqual(
            notes,
            [f"Merging {oldest.display_number}, {newer.display_number} into {oldest.display_number} (the oldest)."],
        )
