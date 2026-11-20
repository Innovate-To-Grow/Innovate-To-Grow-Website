"""The sending jobs: ``helpdesk.send_reply`` (sends a stored reply once, with the subject token and ticket header;
re-checks shadow mode, the ticket and the acknowledgement switch; maps provider errors to job errors), its state
handler (a failed or uncertain job marks the message failed), and ``helpdesk.notify_staff``. No provider is reached:
the email facade's ``deliver_email`` is patched."""

import uuid
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.core.models import BackgroundJob
from apps.core.services.aws.provider_outcomes import ProviderDeliveryError
from apps.core.services.background_jobs import PermanentJobError, TransientJobError, registered_job_kinds
from apps.core.services.email import DeliveryResult

from ...models import HelpdeskSettings, Ticket, TicketEvent, TicketMessage
from ...services import outbound
from ...services.outbound import compose, jobs
from ..helpers import helpdesk_staff
from .support import Status, new_ticket, sending_settings

DELIVER = "apps.core.services.email.deliver_email"
Delivery = TicketMessage.Delivery


def delivered(message, **kwargs):
    kwargs["before_provider_call"]()
    return DeliveryResult(provider="ses", message_id="m-1")


def claimed(job: BackgroundJob) -> BackgroundJob:
    BackgroundJob.objects.filter(pk=job.pk).update(status=BackgroundJob.Status.PROCESSING, claim_token=uuid.uuid4())
    job.refresh_from_db()
    return job


@override_settings(BACKGROUND_JOBS_ENABLED=True)
class JobTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.settings = sending_settings(send_acknowledgement=True)
        self.agent = helpdesk_staff()
        self.ticket = new_ticket(subject="Judging", participants=["pat@example.org"])
        self.inbound = TicketMessage.objects.create(
            ticket=self.ticket,
            kind=TicketMessage.Kind.CUSTOMER,
            from_address="pat@example.org",
            from_name="Pat Doe",
            occurred_at=self.ticket.created_at,
            body_text="Can I judge this year?",
        )

    def queue(self, **values):
        values.setdefault("body", "Yes, please register.")
        with self.captureOnCommitCallbacks(execute=True):
            message = outbound.queue_reply(self.ticket, actor=self.agent, **values)
        return message, claimed(BackgroundJob.objects.get(dedupe_key=f"reply:{message.pk}"))

    def run_job(self, job, side_effect=delivered):
        with patch(DELIVER, side_effect=side_effect) as deliver:
            jobs.send_reply_job(job)
        return deliver


class RegistrationTests(TestCase):
    def test_both_kinds_are_registered_with_their_handlers(self):
        kinds = registered_job_kinds()

        self.assertIn(jobs.REPLY_JOB_KIND, kinds)
        self.assertIn(jobs.NOTIFY_JOB_KIND, kinds)


class SendReplyJobTests(JobTestCase):
    def test_sends_with_the_subject_token_and_ticket_header_and_marks_it_sent(self):
        message, job = self.queue(cc="kim@example.org")

        deliver = self.run_job(job)

        email = deliver.call_args.args[0]
        self.assertEqual(email.subject, f"Re: Judging [{self.ticket.display_number}]")
        self.assertEqual((email.to, email.cc), (("pat@example.org",), ("kim@example.org",)))
        self.assertEqual(email.headers, {"X-I2G-Ticket": self.ticket.display_number})
        self.assertIn("Yes, please register.", email.text_body)
        self.assertIn(compose.footer(self.ticket), email.text_body)
        self.assertIn("Can I judge this year?", email.html_body)  # the requester's message, quoted
        message.refresh_from_db()
        self.assertEqual((message.delivery_status, message.delivery_error), (Delivery.SENT, ""))
        self.assertIsNotNone(message.delivered_at)
        job.refresh_from_db()
        self.assertIsNotNone(job.provider_call_started_at)

    def test_an_acknowledgement_carries_the_automatic_headers_and_quotes_nothing(self):
        ack = TicketMessage.objects.create(
            ticket=self.ticket,
            kind=TicketMessage.Kind.REPLY,
            automatic=True,
            to_addresses=["pat@example.org"],
            subject="",
            occurred_at=self.ticket.created_at,
            body_text="We have your message.",
            delivery_status=Delivery.QUEUED,
        )
        job = claimed(jobs.enqueue_reply(ack))

        email = self.run_job(job).call_args.args[0]

        self.assertEqual(
            email.headers,
            {
                "X-I2G-Ticket": self.ticket.display_number,
                "Auto-Submitted": "auto-replied",
                "X-Auto-Response-Suppress": "All",
            },
        )
        self.assertEqual(email.subject, compose.reply_subject(self.ticket))  # none stored: composed
        self.assertNotIn("Can I judge this year?", email.html_body)
        ack.refresh_from_db()
        self.assertEqual(ack.delivery_status, Delivery.SENT)

    def test_a_message_already_sent_or_gone_or_not_a_reply_is_skipped(self):
        message, job = self.queue()
        TicketMessage.objects.filter(pk=message.pk).update(delivery_status=Delivery.SENT)

        self.run_job(job).assert_not_called()
        for payload in ({"message_id": str(uuid.uuid4())}, {"message_id": str(self.inbound.pk)}):
            job.payload = payload
            with self.subTest(payload):
                self.run_job(job).assert_not_called()

    def test_shadow_mode_switched_back_on_fails_it_with_an_entry(self):
        message, job = self.queue()
        HelpdeskSettings.objects.update(shadow_mode=True)

        self.run_job(job).assert_not_called()

        message.refresh_from_db()
        self.assertEqual((message.delivery_status, message.delivery_error), (Delivery.FAILED, jobs.SHADOW_ON_ERROR))
        failed = self.ticket.events.get(kind=TicketEvent.Kind.REPLY_FAILED)
        self.assertEqual(failed.data, {"what": "reply", "error": jobs.SHADOW_ON_ERROR})

    def test_a_ticket_merged_or_spam_meanwhile_fails_it(self):
        for values in ({"status": Status.MERGED}, {"status": Status.SPAM}, {"automated": True}):
            Ticket.objects.filter(pk=self.ticket.pk).update(status=Status.NEW, automated=False)
            message, job = self.queue()
            Ticket.objects.filter(pk=self.ticket.pk).update(**values)
            with self.subTest(values):
                self.run_job(job).assert_not_called()
                message.refresh_from_db()
                self.assertEqual(message.delivery_status, Delivery.FAILED)
                self.assertIn("merged, marked as spam", message.delivery_error)

    def test_an_acknowledgement_switched_off_meanwhile_fails_it(self):
        ack = TicketMessage.objects.create(
            ticket=self.ticket,
            kind=TicketMessage.Kind.REPLY,
            automatic=True,
            to_addresses=["pat@example.org"],
            occurred_at=self.ticket.created_at,
            body_text="We have your message.",
            delivery_status=Delivery.QUEUED,
        )
        job = claimed(jobs.enqueue_reply(ack))
        HelpdeskSettings.objects.update(send_acknowledgement=False)

        self.run_job(job).assert_not_called()

        ack.refresh_from_db()
        self.assertEqual(ack.delivery_status, Delivery.FAILED)
        self.assertEqual(self.ticket.events.get(kind=TicketEvent.Kind.REPLY_FAILED).data["what"], "acknowledgement")

    def test_a_provider_error_becomes_the_matching_job_error_and_leaves_it_queued(self):
        for outcome, error in (("transient", TransientJobError), ("permanent", PermanentJobError)):
            message, job = self.queue(body=f"Attempt {outcome}")
            with self.subTest(outcome), self.assertRaises(error):
                self.run_job(job, side_effect=ProviderDeliveryError("refused", outcome=outcome))
            message.refresh_from_db()
            self.assertEqual(message.delivery_status, Delivery.QUEUED)


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
        from ...models import AssignmentGroup

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
