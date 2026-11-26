"""The first response is a staff reply going out, judged when the job sends it: queued is no response yet (a reply
that never goes out answers nobody). The job records it with the reply's author and, when the response fell due
before the reply went out, the breach; an acknowledgement, a reply that did not go out and a second reply are no first
response, and a breach the worker flagged meanwhile is not recorded twice. No provider is reached: the email facade's
``deliver_email`` is patched."""

from datetime import timedelta

from django.utils import timezone

from apps.core.models import BackgroundJob

from ....models import HelpdeskSettings, Ticket, TicketEvent, TicketMessage
from ....services import sla, tickets
from ....services.outbound import jobs
from ...helpers.service import Status, clocked_ticket, new_ticket
from ..outbound.test_jobs import JobTestCase, claimed

Kind = TicketEvent.Kind
Delivery = TicketMessage.Delivery


class FirstResponseTests(JobTestCase):
    def setUp(self):
        super().setUp()
        # Moderate priority: the response is due 24 h after the start, here in 2 h.
        self.ticket = clocked_ticket(subject="Judging", started=timezone.now() - timedelta(hours=22))

    def due_time_passes(self):
        """The response falls due while the reply waits in the queue."""
        Ticket.objects.filter(pk=self.ticket.pk).update(response_due_at=timezone.now() - timedelta(minutes=1))

    def data(self, kind):
        return list(self.ticket.events.filter(kind=kind).values_list("data", flat=True))

    def test_queued_is_no_response_and_sent_is_one(self):
        message, job = self.queue()
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.first_responded_at)
        self.assertEqual(sla.current_clock(self.ticket, timezone.now(), 75)[0], "Response")  # still running

        self.run_job(job)

        message.refresh_from_db()
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.first_responded_at, message.delivered_at)
        self.assertFalse(self.ticket.response_breached)
        self.assertEqual(sla.response_clock(self.ticket, timezone.now(), 75).state, "met")
        responded = self.ticket.events.get(kind=Kind.RESPONDED)
        self.assertEqual((responded.actor, responded.data), (self.agent, {"by": "reply"}))  # the reply's author
        self.assertEqual(self.data(Kind.SLA_BREACHED), [])

    def test_queued_in_time_but_sent_after_the_due_time_is_a_late_response(self):
        _message, job = self.queue()
        self.due_time_passes()

        self.run_job(job)

        self.ticket.refresh_from_db()
        self.assertIsNotNone(self.ticket.first_responded_at)
        self.assertTrue(self.ticket.response_breached)
        self.assertEqual(self.data(Kind.SLA_BREACHED), [{"which": "response"}])
        self.assertEqual(sla.response_clock(self.ticket, timezone.now(), 75).state, "breached")

    def test_a_breach_the_worker_flagged_meanwhile_is_recorded_once(self):
        _message, job = self.queue()
        self.due_time_passes()
        self.assertEqual(sla.mark_breaches(), 1)

        self.run_job(job)

        self.ticket.refresh_from_db()
        self.assertIsNotNone(self.ticket.first_responded_at)
        self.assertTrue(self.ticket.response_breached)
        self.assertEqual(self.data(Kind.SLA_BREACHED), [{"which": "response"}])
        self.assertEqual(self.data(Kind.RESPONDED), [{"by": "reply"}])

    def test_the_replys_own_move_out_of_new_waits_for_the_send(self):
        message, job = self.queue(status=Status.OPEN)
        self.ticket.refresh_from_db()
        self.assertEqual((self.ticket.status, self.ticket.first_responded_at), (Status.OPEN, None))
        self.assertEqual(self.data(Kind.RESPONDED), [])

        self.run_job(job)

        self.ticket.refresh_from_db()
        message.refresh_from_db()
        self.assertEqual(self.ticket.first_responded_at, message.delivered_at)
        self.assertEqual(self.data(Kind.RESPONDED), [{"by": "reply"}])

    def test_a_reply_that_does_not_go_out_is_no_response(self):
        _failed, failed_job = self.queue()
        BackgroundJob.objects.filter(pk=failed_job.pk).update(status=BackgroundJob.Status.FAILED)
        failed_job.refresh_from_db()
        jobs.reply_job_state(failed_job)
        _stopped, stopped_job = self.queue(body="Trying again.")
        HelpdeskSettings.objects.update(shadow_mode=True)

        self.run_job(stopped_job).assert_not_called()

        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.first_responded_at)
        self.assertEqual(self.data(Kind.RESPONDED), [])
        self.due_time_passes()
        self.assertEqual(sla.mark_breaches(), 1)  # still unanswered: the worker flags it

    def test_an_acknowledgement_sent_is_no_response(self):
        ack = TicketMessage.objects.create(
            ticket=self.ticket,
            kind=TicketMessage.Kind.REPLY,
            automatic=True,
            to_addresses=["pat@example.org"],
            occurred_at=timezone.now(),
            body_text="We have your message.",
            delivery_status=Delivery.QUEUED,
        )

        self.run_job(claimed(jobs.enqueue_reply(ack)))

        ack.refresh_from_db()
        self.ticket.refresh_from_db()
        self.assertEqual(ack.delivery_status, Delivery.SENT)
        self.assertIsNone(self.ticket.first_responded_at)
        self.assertEqual(self.data(Kind.RESPONDED), [])

    def test_a_ticket_moved_on_before_the_reply_went_out_keeps_that_response(self):
        _message, job = self.queue()
        tickets.update_ticket(self.ticket, actor=self.agent, status=Status.PENDING_INTERNAL)
        self.ticket.refresh_from_db()
        moved_on = self.ticket.first_responded_at

        self.run_job(job)

        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.first_responded_at, moved_on)
        self.assertEqual(self.data(Kind.RESPONDED), [{"by": "status"}])

    def test_a_ticket_without_a_clock_records_the_response_and_no_breach(self):
        self.ticket = new_ticket(subject="Judging")

        message, job = self.queue()
        self.run_job(job)

        message.refresh_from_db()
        self.ticket.refresh_from_db()
        self.assertEqual((self.ticket.first_responded_at, self.ticket.response_breached), (message.delivered_at, False))
        self.assertEqual(self.data(Kind.RESPONDED), [{"by": "reply"}])
        self.assertEqual(self.data(Kind.SLA_BREACHED), [])
