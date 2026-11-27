"""The state handler of ``helpdesk.send_reply`` (a failed job marks the reply failed, an uncertain one marks it not
confirmed, each with a fixed text and a timeline entry), ``helpdesk.notify_staff`` (it sends nothing any more: staff
get no helpdesk email, I2G-HELPDESK-01; a notice an earlier release queued finishes quietly), and the registration of
both kinds. No provider is reached: the email facade's ``deliver_email`` is patched."""

import uuid
from unittest.mock import patch

from django.test import TestCase
from django.utils.module_loading import import_string

from apps.core.models import BackgroundJob
from apps.core.services.background_jobs import enqueue_job, registered_job_kinds

from ....models import TicketEvent, TicketMessage
from ....services.outbound import jobs
from .test_jobs import DELIVER, JobTestCase, claimed

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
        self.assertIn("An Admin can see the details in Email Monitoring.", message.delivery_error)
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
    def test_a_notice_an_earlier_release_queued_sends_nothing(self):
        payload = {"ticket_id": str(self.ticket.pk), "recipients": ["agent@example.com"], "reason": "assigned"}
        job, _created = enqueue_job(kind=jobs.NOTIFY_JOB_KIND, dedupe_key="notify:old", payload=payload)

        with patch(DELIVER) as deliver:
            jobs.notify_staff_job(claimed(job))

        deliver.assert_not_called()
        self.assertFalse(self.ticket.events.filter(kind=Kind.NOTIFIED).exists())


class RegistrationTests(TestCase):
    def test_both_kinds_are_registered_with_their_handlers(self):
        kinds = registered_job_kinds()

        self.assertEqual(kinds[jobs.REPLY_JOB_KIND].handler, "apps.helpdesk.services.outbound.jobs.send_reply_job")
        notify = kinds[jobs.NOTIFY_JOB_KIND]
        self.assertEqual(notify.handler, "apps.helpdesk.services.outbound.jobs.notify_staff_job")
        self.assertIs(import_string(notify.handler), jobs.notify_staff_job)
        # It sends nothing, so it is on no delivery lane.
        self.assertEqual((notify.family, notify.lane), (None, None))
