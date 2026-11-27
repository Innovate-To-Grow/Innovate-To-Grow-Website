"""The sending jobs: ``helpdesk.send_reply`` (sends a stored reply once, with the subject token and ticket header;
re-checks shadow mode, the ticket and the acknowledgement switch; maps provider errors to job errors), its state
handler (a failed or uncertain job marks the message failed). No provider is reached:
the email facade's ``deliver_email`` is patched."""

import uuid
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.core.models import BackgroundJob
from apps.core.services.aws.provider_outcomes import ProviderDeliveryError
from apps.core.services.background_jobs import PermanentJobError, TransientJobError
from apps.core.services.email import DeliveryResult

from ....models import HelpdeskSettings, Ticket, TicketEvent, TicketMessage
from ....services import outbound
from ....services.outbound import compose, jobs
from ...helpers import helpdesk_staff
from ...helpers.service import Status, new_ticket, sending_settings

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


class SendReplyJobTests(JobTestCase):
    def test_sends_with_the_subject_token_and_ticket_header_and_marks_it_sent(self):
        message, job = self.queue(cc="kim@example.org")

        TicketMessage.objects.create(
            ticket=self.ticket,
            kind=TicketMessage.Kind.CUSTOMER,
            from_address=self.inbound.from_address,
            occurred_at=message.occurred_at,
            body_text="Private follow-up",
        )
        deliver = self.run_job(job)

        email = deliver.call_args.args[0]
        self.assertEqual(email.subject, f"Re: Judging [{self.ticket.display_number}]")
        self.assertEqual((email.to, email.cc), (("pat@example.org",), ("kim@example.org",)))
        self.assertEqual(email.headers, {"X-I2G-Ticket": self.ticket.display_number})
        self.assertEqual(email.reply_to, ())  # no inbound mailbox known: answers go to the From address
        self.assertNotIn("Private follow-up", email.html_body)
        self.assertNotIn("Private follow-up", email.text_body)
        self.assertIn("Yes, please register.", email.text_body)
        self.assertIn(compose.footer(self.ticket), email.text_body)
        self.assertIn("Can I judge this year?", email.html_body)  # the requester's message, quoted
        self.assertIn("Pat Doe wrote:\n> Can I judge this year?", email.text_body)  # in the text part too
        message.refresh_from_db()
        self.assertEqual((message.delivery_status, message.delivery_error), (Delivery.SENT, ""))
        self.assertIsNotNone(message.delivered_at)
        job.refresh_from_db()
        self.assertIsNotNone(job.provider_call_started_at)

    def test_queued_reply_stops_if_a_recipient_is_identified_as_a_list(self):
        message, job = self.queue(cc="group@example.org")
        self.ticket.messages.filter(pk=self.inbound.pk).update(list_address="group@example.org")
        self.run_job(job).assert_not_called()
        message.refresh_from_db()
        self.assertEqual(message.delivery_status, Delivery.FAILED)

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

    def test_only_a_reply_still_queued_is_sent(self):
        message, job = self.queue()
        for status in (Delivery.SENT, Delivery.FAILED, Delivery.UNCERTAIN, ""):
            TicketMessage.objects.filter(pk=message.pk).update(delivery_status=status)
            with self.subTest(status):
                self.run_job(job).assert_not_called()
                message.refresh_from_db()
                self.assertEqual(message.delivery_status, status)
        self.assertFalse(self.ticket.events.filter(kind=TicketEvent.Kind.REPLY_FAILED).exists())
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
