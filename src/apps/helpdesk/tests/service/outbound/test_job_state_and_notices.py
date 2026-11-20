"""The sending jobs: ``helpdesk.send_reply`` (sends a stored reply once, with the subject token and ticket header;
re-checks shadow mode, the ticket and the acknowledgement switch; maps provider errors to job errors), its state
handler (a failed or uncertain job marks the message failed), and ``helpdesk.notify_staff``. No provider is reached:
the email facade's ``deliver_email`` is patched."""

import uuid
from unittest.mock import patch

from apps.core.models import BackgroundJob
from apps.core.services.aws.provider_outcomes import ProviderDeliveryError
from apps.core.services.background_jobs import TransientJobError
from apps.core.services.email import DeliveryResult

from ....models import HelpdeskSettings, Ticket, TicketEvent, TicketMessage
from ....services.outbound import compose, jobs
from .test_jobs import JobTestCase

DELIVER = "apps.core.services.email.deliver_email"
Delivery = TicketMessage.Delivery


def delivered(message, **kwargs):
    kwargs["before_provider_call"]()
    return DeliveryResult(provider="ses", message_id="m-1")


def claimed(job: BackgroundJob) -> BackgroundJob:
    BackgroundJob.objects.filter(pk=job.pk).update(status=BackgroundJob.Status.PROCESSING, claim_token=uuid.uuid4())
    job.refresh_from_db()
    return job


class ReplyJobStateTests(JobTestCase):
    def finish(self, status):
        message, job = self.queue()
        BackgroundJob.objects.filter(pk=job.pk).update(status=status)
        job.refresh_from_db()
        jobs.reply_job_state(job)
        message.refresh_from_db()
        return message

    def test_a_failed_job_marks_the_reply_failed_without_provider_detail(self):
        message = self.finish(BackgroundJob.Status.FAILED)

        self.assertEqual(message.delivery_status, Delivery.FAILED)
        self.assertIn("See Email Monitoring", message.delivery_error)
        self.assertEqual(self.ticket.events.filter(kind=TicketEvent.Kind.REPLY_FAILED).count(), 1)

    def test_an_uncertain_job_says_it_may_have_gone(self):
        message = self.finish(BackgroundJob.Status.UNCERTAIN)

        self.assertEqual(message.delivery_status, Delivery.FAILED)
        self.assertIn("not certain", message.delivery_error)

    def test_other_states_and_sent_messages_change_nothing(self):
        self.assertEqual(self.finish(BackgroundJob.Status.PROCESSING).delivery_status, Delivery.QUEUED)
        message, job = self.queue(body="Sent already")
        TicketMessage.objects.filter(pk=message.pk).update(delivery_status=Delivery.SENT)
        BackgroundJob.objects.filter(pk=job.pk).update(status=BackgroundJob.Status.FAILED)
        job.refresh_from_db()

        jobs.reply_job_state(job)

        message.refresh_from_db()
        self.assertEqual(message.delivery_status, Delivery.SENT)
        self.assertFalse(self.ticket.events.filter(kind=TicketEvent.Kind.REPLY_FAILED).exists())
        job.payload = {"message_id": str(uuid.uuid4())}
        jobs.reply_job_state(job)  # a message gone meanwhile: nothing to mark


class NotifyStaffJobTests(JobTestCase):
    def notice(self, reason="assigned", recipients=("agent@example.com",)):
        job = jobs.enqueue_notice(self.ticket, recipients=list(recipients), reason=reason, actor_name="Sam Lead")
        return claimed(job)

    def test_the_email_names_the_ticket_and_never_carries_the_message(self):
        with patch(DELIVER, side_effect=delivered) as deliver:
            jobs.notify_staff_job(self.notice())

        email = deliver.call_args.args[0]
        self.assertEqual(email.to, ("agent@example.com",))
        self.assertEqual(email.subject, f"[{self.ticket.display_number}] Assigned to you: Judging")
        self.assertIn(f"Sam Lead assigned {self.ticket.display_number} to you.", email.text_body)
        self.assertIn(compose.ticket_admin_url(self.ticket), email.text_body)
        self.assertIn("Requester: pat@example.org", email.text_body)
        self.assertNotIn("Can I judge this year?", email.text_body)
        self.assertIsNone(email.html_body)

    def test_a_group_notice_names_the_group(self):
        from ....models import AssignmentGroup

        Ticket.objects.filter(pk=self.ticket.pk).update(assignment_group=AssignmentGroup.objects.create(name="Events"))

        with patch(DELIVER, side_effect=delivered) as deliver:
            jobs.notify_staff_job(self.notice(reason="group"))

        email = deliver.call_args.args[0]
        self.assertTrue(email.subject.startswith(f"[{self.ticket.display_number}] Assigned to your group"))
        self.assertIn("to Events.", email.text_body)

    def test_nothing_is_sent_in_shadow_mode_or_without_a_ticket_or_recipients(self):
        job = self.notice()
        HelpdeskSettings.objects.update(shadow_mode=True)
        with patch(DELIVER) as deliver:
            jobs.notify_staff_job(job)
            HelpdeskSettings.objects.update(shadow_mode=False)
            job.payload = {**job.payload, "ticket_id": str(uuid.uuid4())}
            jobs.notify_staff_job(job)
            job.payload = {**job.payload, "ticket_id": str(self.ticket.pk), "recipients": []}
            jobs.notify_staff_job(job)
        deliver.assert_not_called()
        self.assertIsNone(jobs.enqueue_notice(self.ticket, recipients=[], reason="assigned"))

    def test_a_provider_error_becomes_a_job_error(self):
        with (
            patch(DELIVER, side_effect=ProviderDeliveryError("down", outcome="transient")),
            self.assertRaises(TransientJobError),
        ):
            jobs.notify_staff_job(self.notice())
