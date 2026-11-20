"""A staff reply that does not go out puts its ticket back in front of staff: failed, not confirmed, or stopped by the
job's re-check (shadow mode switched on meanwhile, the ticket marked spam or merged), a ticket that was waiting for
the requester is In progress again with the reason on its timeline (its clock running again), and the ticket is
unread. An acknowledgement that does not go out changes nothing on its ticket. Each reply is marked once."""

from apps.core.models import BackgroundJob

from ....models import HelpdeskSettings, Ticket, TicketEvent, TicketMessage
from ....services.outbound import jobs
from ....services.tickets import events
from ...helpers.service import Status, clocked_ticket
from ..outbound.test_jobs import JobTestCase, claimed

Kind = TicketEvent.Kind
Delivery = TicketMessage.Delivery
WAITING = Status.PENDING_CUSTOMER


def finish(job, status) -> None:
    """The worker gives up on ``job`` (``status``) and calls the reply's state handler."""
    BackgroundJob.objects.filter(pk=job.pk).update(status=status)
    job.refresh_from_db()
    jobs.reply_job_state(job)


class UndeliveredReplyTests(JobTestCase):
    def setUp(self):
        super().setUp()
        self.ticket = clocked_ticket(subject="Judging")

    def waiting_reply(self, **values):
        """A reply sent with "On hold – awaiting requester", on a ticket staff have read since."""
        message, job = self.queue(status=WAITING, **values)
        Ticket.objects.filter(pk=self.ticket.pk).update(unread=False)
        self.ticket.refresh_from_db()
        self.assertIsNotNone(self.ticket.sla_paused_at)
        return message, job

    def assert_back_in_front_of_staff(self):
        self.ticket.refresh_from_db()
        self.assertEqual((self.ticket.status, self.ticket.unread), (Status.OPEN, True))
        self.assertIsNone(self.ticket.sla_paused_at)  # the resolution clock runs again
        back = [event for event in self.ticket.events.filter(kind=Kind.STATUS) if event.data["from"] == WAITING]
        self.assertEqual(len(back), 1)
        expected = {"from": WAITING, "to": Status.OPEN, "reason": "the reply did not go out"}
        self.assertEqual((back[0].actor, back[0].data), (None, expected))
        self.assertEqual(
            events.describe(back[0]),
            "Status changed: On hold – awaiting requester → In progress (the reply did not go out)",
        )

    def failure(self) -> str:
        return events.describe(self.ticket.events.get(kind=Kind.REPLY_FAILED))

    def test_a_failed_reply(self):
        message, job = self.waiting_reply()

        finish(job, BackgroundJob.Status.FAILED)

        self.assert_back_in_front_of_staff()
        message.refresh_from_db()
        self.assertEqual(message.delivery_status, Delivery.FAILED)
        self.assertEqual(self.failure(), f"The reply was not sent: {jobs.FAILED_ERROR}")

    def test_a_reply_the_mail_service_did_not_confirm(self):
        message, job = self.waiting_reply()

        finish(job, BackgroundJob.Status.UNCERTAIN)

        self.assert_back_in_front_of_staff()
        message.refresh_from_db()
        self.assertEqual(message.delivery_status, Delivery.UNCERTAIN)
        self.assertEqual(self.failure(), f"The reply may not have been delivered: {jobs.UNCERTAIN_ERROR}")

    def test_a_reply_stopped_because_shadow_mode_was_switched_on(self):
        message, job = self.waiting_reply()
        HelpdeskSettings.objects.update(shadow_mode=True)

        self.run_job(job).assert_not_called()

        self.assert_back_in_front_of_staff()
        message.refresh_from_db()
        self.assertEqual((message.delivery_status, message.delivery_error), (Delivery.FAILED, jobs.SHADOW_ON_ERROR))
        self.assertEqual(self.failure(), "The reply was not sent: shadow mode was switched on before it went out.")

    def test_a_reply_stopped_because_the_ticket_was_marked_spam_or_merged(self):
        for status in (Status.SPAM, Status.MERGED):
            Ticket.objects.filter(pk=self.ticket.pk).update(status=Status.NEW)
            self.ticket.refresh_from_db()
            message, job = self.queue(body=f"About {status}.")
            Ticket.objects.filter(pk=self.ticket.pk).update(status=status, unread=False)
            with self.subTest(status):
                self.run_job(job).assert_not_called()

                message.refresh_from_db()
                self.ticket.refresh_from_db()
                self.assertEqual(message.delivery_status, Delivery.FAILED)
                self.assertEqual((self.ticket.status, self.ticket.unread), (status, True))

    def test_a_ticket_that_was_not_waiting_keeps_its_status_and_is_unread(self):
        _message, job = self.queue()  # no status chosen: still New
        Ticket.objects.filter(pk=self.ticket.pk).update(unread=False)

        finish(job, BackgroundJob.Status.FAILED)

        self.ticket.refresh_from_db()
        self.assertEqual((self.ticket.status, self.ticket.unread), (Status.NEW, True))
        self.assertFalse(self.ticket.events.filter(kind=Kind.STATUS).exists())

    def test_a_reply_is_marked_once(self):
        message, job = self.waiting_reply()

        finish(job, BackgroundJob.Status.FAILED)
        finish(job, BackgroundJob.Status.UNCERTAIN)  # a later state of the same job changes nothing
        self.run_job(job).assert_not_called()

        message.refresh_from_db()
        self.assertEqual(message.delivery_status, Delivery.FAILED)
        self.assertEqual(self.ticket.events.filter(kind=Kind.REPLY_FAILED).count(), 1)
        self.assertEqual(self.ticket.events.filter(kind=Kind.STATUS).count(), 2)  # on hold with it, back once


class UndeliveredAcknowledgementTests(JobTestCase):
    def setUp(self):
        super().setUp()
        Ticket.objects.filter(pk=self.ticket.pk).update(status=WAITING, unread=False)
        self.ack = TicketMessage.objects.create(
            ticket=self.ticket,
            kind=TicketMessage.Kind.REPLY,
            automatic=True,
            to_addresses=["pat@example.org"],
            occurred_at=self.ticket.created_at,
            body_text="We have your message.",
            delivery_status=Delivery.QUEUED,
        )
        self.job = claimed(jobs.enqueue_reply(self.ack))

    def assert_ticket_unchanged(self, error):
        self.ticket.refresh_from_db()
        self.ack.refresh_from_db()
        self.assertEqual((self.ticket.status, self.ticket.unread), (WAITING, False))
        self.assertFalse(self.ticket.events.filter(kind=Kind.STATUS).exists())
        self.assertEqual(self.ack.delivery_error, error)
        failed = self.ticket.events.get(kind=Kind.REPLY_FAILED)
        self.assertEqual(failed.data["what"], "acknowledgement")
        self.assertTrue(events.describe(failed).startswith("The acknowledgement "))

    def test_a_failed_acknowledgement(self):
        finish(self.job, BackgroundJob.Status.FAILED)

        self.assert_ticket_unchanged(jobs.FAILED_ERROR)

    def test_an_acknowledgement_not_confirmed(self):
        finish(self.job, BackgroundJob.Status.UNCERTAIN)

        self.assert_ticket_unchanged(jobs.UNCERTAIN_ERROR)
        self.assertEqual(self.ack.delivery_status, Delivery.UNCERTAIN)

    def test_an_acknowledgement_stopped_by_shadow_mode(self):
        HelpdeskSettings.objects.update(shadow_mode=True)

        self.run_job(self.job).assert_not_called()

        self.assert_ticket_unchanged(jobs.SHADOW_ON_ERROR)
