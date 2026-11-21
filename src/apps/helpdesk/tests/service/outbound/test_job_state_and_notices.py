"""The state handler of ``helpdesk.send_reply`` (a failed job marks the reply failed, an uncertain one marks it not
confirmed, each with a fixed text and a timeline entry), and ``helpdesk.notify_staff`` (``notifications``): what a
notice says, and that the timeline records it once it went out. No provider is reached: the email facade's
``deliver_email`` is patched."""

import uuid
from unittest.mock import patch

from apps.core.models import BackgroundJob
from apps.core.services.aws.provider_outcomes import ProviderDeliveryError
from apps.core.services.background_jobs import TransientJobError

from ....models import AssignmentGroup, HelpdeskSettings, Ticket, TicketEvent, TicketMessage
from ....services.outbound import compose, jobs, notifications
from .test_jobs import DELIVER, JobTestCase, claimed, delivered

Delivery = TicketMessage.Delivery
Kind = TicketEvent.Kind


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

        self.assertEqual((message.delivery_status, message.delivery_error), (Delivery.FAILED, jobs.FAILED_ERROR))
        self.assertIn("An I2G Master can see the details in Email Monitoring.", message.delivery_error)
        failed = self.ticket.events.get(kind=Kind.REPLY_FAILED)
        self.assertEqual(failed.data, {"what": "reply", "error": jobs.FAILED_ERROR})

    def test_an_uncertain_job_marks_the_reply_not_confirmed(self):
        message = self.finish(BackgroundJob.Status.UNCERTAIN)

        self.assertEqual((message.delivery_status, message.delivery_error), (Delivery.UNCERTAIN, jobs.UNCERTAIN_ERROR))
        self.assertEqual(message.get_delivery_status_display(), "Not confirmed")
        failed = self.ticket.events.get(kind=Kind.REPLY_FAILED)
        self.assertEqual(failed.data, {"what": "reply", "error": jobs.UNCERTAIN_ERROR, "uncertain": True})

    def test_other_states_and_sent_messages_change_nothing(self):
        self.assertEqual(self.finish(BackgroundJob.Status.PROCESSING).delivery_status, Delivery.QUEUED)
        message, job = self.queue(body="Sent already")
        TicketMessage.objects.filter(pk=message.pk).update(delivery_status=Delivery.SENT)
        BackgroundJob.objects.filter(pk=job.pk).update(status=BackgroundJob.Status.FAILED)
        job.refresh_from_db()

        jobs.reply_job_state(job)

        message.refresh_from_db()
        self.assertEqual(message.delivery_status, Delivery.SENT)
        self.assertFalse(self.ticket.events.filter(kind=Kind.REPLY_FAILED).exists())
        job.payload = {"message_id": str(uuid.uuid4())}
        jobs.reply_job_state(job)  # a message gone meanwhile: nothing to mark


class NotifyStaffJobTests(JobTestCase):
    def setUp(self):
        super().setUp()
        Ticket.objects.filter(pk=self.ticket.pk).update(assignee=self.agent)

    def notice(self, reason="assigned", recipients=("agent@example.com",)):
        job = jobs.enqueue_notice(self.ticket, recipients=list(recipients), reason=reason, actor_name="Sam Lead")
        return claimed(job)

    def send(self, job, side_effect=delivered):
        with patch(DELIVER, side_effect=side_effect) as deliver:
            notifications.notify_staff_job(job)
        return deliver

    def test_the_email_names_the_ticket_and_never_carries_the_message(self):
        email = self.send(self.notice()).call_args.args[0]

        self.assertEqual(email.to, ("agent@example.com",))
        self.assertEqual(email.subject, f"[{self.ticket.display_number}] Assigned to you: Judging")
        self.assertIn(f"Sam Lead assigned {self.ticket.display_number} to you.", email.text_body)
        self.assertIn(compose.ticket_admin_url(self.ticket), email.text_body)
        self.assertIn("Requester: pat@example.org", email.text_body)
        self.assertNotIn("Can I judge this year?", email.text_body)
        self.assertIsNone(email.html_body)
        self.assertEqual(email.headers, {"Auto-Submitted": "auto-generated", "X-Auto-Response-Suppress": "All"})
        self.assertIn("This is an automatic notice: please do not reply to it", email.text_body)
        self.assertEqual(self.ticket.events.get(kind=Kind.NOTIFIED).data, {"reason": "assigned", "count": 1})

    def test_the_notice_names_the_ticket_without_a_reply_prefix_or_another_tickets_number(self):
        Ticket.objects.filter(pk=self.ticket.pk).update(subject="Re: Judging [I2G-#1006]")

        email = self.send(self.notice()).call_args.args[0]

        self.assertEqual(email.subject, f"[{self.ticket.display_number}] Assigned to you: Judging")
        self.assertIn("\n\nSubject: Judging\n", email.text_body)
        self.assertNotIn("I2G-#1006", email.text_body)

    def test_a_group_notice_names_the_group(self):
        group = AssignmentGroup.objects.create(name="Events")
        group.members.add(self.agent)
        Ticket.objects.filter(pk=self.ticket.pk).update(assignee=None, assignment_group=group)

        email = self.send(self.notice(reason="group")).call_args.args[0]

        self.assertTrue(email.subject.startswith(f"[{self.ticket.display_number}] Assigned to your group"))
        self.assertIn("Sam Lead assigned", email.text_body)
        self.assertIn("to Events.", email.text_body)
        self.assertEqual(self.ticket.events.get(kind=Kind.NOTIFIED).data, {"reason": "group", "count": 1})

    def test_nothing_is_sent_in_shadow_mode_or_without_a_ticket_or_recipients(self):
        job = self.notice()
        HelpdeskSettings.objects.update(shadow_mode=True)
        with patch(DELIVER) as deliver:
            notifications.notify_staff_job(job)
            HelpdeskSettings.objects.update(shadow_mode=False)
            job.payload = {**job.payload, "ticket_id": str(uuid.uuid4())}
            notifications.notify_staff_job(job)
            job.payload = {**job.payload, "ticket_id": str(self.ticket.pk), "recipients": []}
            notifications.notify_staff_job(job)
        deliver.assert_not_called()
        self.assertFalse(self.ticket.events.filter(kind=Kind.NOTIFIED).exists())
        self.assertIsNone(jobs.enqueue_notice(self.ticket, recipients=[], reason="assigned"))

    def test_a_provider_error_becomes_a_job_error_and_records_no_notice(self):
        with self.assertRaises(TransientJobError):
            self.send(self.notice(), side_effect=ProviderDeliveryError("down", outcome="transient"))

        self.assertFalse(self.ticket.events.filter(kind=Kind.NOTIFIED).exists())
