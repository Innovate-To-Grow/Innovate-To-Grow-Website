"""Ticket texts for phone-only registrants: who gets one (off by default), how the first ticket's signal queues it
inside the registration's transaction, and what the job does with each outcome. ``send_text_message`` stands in for
AWS; nothing is sent."""

from unittest.mock import patch

from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.authn.models import Member
from apps.core.models import BackgroundJob
from apps.core.services.aws.sms_errors import SmsDeliveryError, SmsOptedOut
from apps.core.services.background_jobs import claim_jobs, process_claimed_job
from apps.core.services.delivery_rates import Lane
from apps.event.signals import initial_ticket_issued
from apps.event.tests.helpers import make_event, make_member, make_registration, make_ticket
from apps.event.views.registration.create_support.notifications import send_initial_ticket_email
from apps.mail.models import SmsLinkToken, TicketSms
from apps.mail.services.sms import ticket
from apps.mail.services.sms.opt_outs import SKIPPED_MESSAGE
from apps.mail.services.sms.quiet_hours import HELD_LOG_MESSAGE

from .policy_helpers import QUIET_ENDS, QUIET_MOMENT, add_phone, at, opt_out, sms_aws_config, sms_settings

SEND = "apps.mail.services.sms.ticket.send_text_message"
PHONE = "+12095550101"


class TicketSmsTestCase(TestCase):
    def setUp(self):
        sms_aws_config()
        self.event = make_event(name="Fall Demo", registration_open=True)
        self.ticket = make_ticket(self.event)
        self.member = Member.objects.create_user(password="testpass123", first_name="Pho")
        self.phone = add_phone(self.member, "2095550101")
        self.registration = make_registration(self.member, self.event, self.ticket)

    def turn_on(self, **values):
        return sms_settings(links_enabled=True, ticket_sms_enabled=True, **values)

    def queue(self):
        return ticket.queue_ticket_sms(registration=self.registration)


@override_settings(BACKGROUND_JOBS_ENABLED=True)
class QueueTicketSmsTests(TicketSmsTestCase):
    def test_ticket_texts_are_off_by_default(self):
        self.assertEqual(self.registration.attendee_email, "")
        self.assertIsNone(self.queue())
        self.assertFalse(TicketSms.objects.exists())

    def test_a_phone_only_registrant_with_a_verified_phone_gets_one_queued(self):
        self.turn_on()
        record = self.queue()
        self.assertEqual((record.phone_number, record.status), (PHONE, "pending"))
        job = BackgroundJob.objects.get(kind="mail.ticket_sms")
        self.assertEqual(job.payload, {"ticket_sms_id": str(record.pk)})
        # A second signal for the same registration queues nothing more.
        self.assertEqual(self.queue(), record)
        self.assertEqual(BackgroundJob.objects.filter(kind="mail.ticket_sms").count(), 1)

    def test_in_quiet_hours_it_is_due_when_they_end(self):
        self.turn_on()
        with at(QUIET_MOMENT):
            record = self.queue()
        self.assertEqual(record.available_at, QUIET_ENDS)
        self.assertEqual(BackgroundJob.objects.get(kind="mail.ticket_sms").available_at, QUIET_ENDS)

    def test_registrants_with_an_email_or_without_a_verified_phone_get_none(self):
        self.turn_on()
        emailed = make_member(email="ada@example.com")
        add_phone(emailed, "2095550102")
        with_email = make_registration(emailed, self.event, self.ticket)
        self.assertIsNone(ticket.queue_ticket_sms(registration=with_email))
        self.phone.verified = False
        self.phone.save(update_fields=["verified"])
        self.assertIsNone(self.queue())
        self.assertFalse(TicketSms.objects.exists())

    def test_the_phone_verified_for_the_registration_comes_first(self):
        self.turn_on()
        self.registration.attendee_phone = "+12095550199"
        self.registration.phone_verified = True
        self.registration.save()
        self.assertEqual(self.queue().phone_number, "+12095550199")

    def test_links_off_means_no_ticket_text(self):
        sms_settings(ticket_sms_enabled=True)
        self.assertIsNone(self.queue())

    def test_a_failure_never_breaks_the_registration_transaction(self):
        self.turn_on()
        with (
            transaction.atomic(),
            patch.object(ticket, "_queue", side_effect=RuntimeError("boom")),
            self.assertLogs("apps.mail.services.sms.ticket", level="ERROR"),
        ):
            self.assertIsNone(self.queue())
            # The transaction is still usable (a broken one would refuse this query on PostgreSQL).
            self.assertEqual(TicketSms.objects.count(), 0)
            self.registration.refresh_from_db()

    def test_the_first_tickets_signal_queues_it_with_the_ticket_email(self):
        self.turn_on()
        with transaction.atomic():
            send_initial_ticket_email(self.registration)
        self.assertTrue(TicketSms.objects.filter(registration=self.registration).exists())
        self.assertEqual(
            set(BackgroundJob.objects.values_list("kind", flat=True)), {"event.ticket_email", "mail.ticket_sms"}
        )

    def test_the_signal_receiver_is_connected(self):
        self.turn_on()
        initial_ticket_issued.send_robust(sender=type(self.registration), registration=self.registration)
        self.assertTrue(TicketSms.objects.exists())


@override_settings(BACKGROUND_JOBS_ENABLED=False)
class InProcessTicketSmsTests(TicketSmsTestCase):
    @patch(SEND, return_value="msg-1")
    def test_without_jobs_it_is_sent_after_the_commit(self, send):
        self.turn_on()
        with (
            patch("apps.mail.services.sms.ticket.start_in_process_task", side_effect=lambda fn, *a, **k: fn(*a)),
            self.captureOnCommitCallbacks(execute=True),
        ):
            record = self.queue()
        record.refresh_from_db()
        self.assertEqual((record.status, record.message_id), ("sent", "msg-1"))
        self.assertIsNone(send.call_args.kwargs["before_provider_call"])

    @patch(SEND)
    def test_without_jobs_quiet_hours_skip_it(self, send):
        self.turn_on()
        record = self.queue()
        with at(QUIET_MOMENT):
            ticket.deliver_ticket_sms(record)
        send.assert_not_called()
        self.assertEqual((record.status, record.error_message), ("skipped", ticket.QUIET_NO_JOBS_MESSAGE))

    @patch(SEND, side_effect=SmsDeliveryError("SMS rejected the request.", outcome="permanent"))
    def test_without_jobs_a_failure_is_recorded(self, _send):
        self.turn_on()
        record = self.queue()
        ticket.deliver_ticket_sms(record)
        self.assertEqual(record.status, "failed")

    def test_a_thread_failure_is_logged_not_raised(self):
        with self.assertLogs("apps.mail.services.sms.ticket", level="ERROR"):
            ticket._send_in_process("00000000-0000-0000-0000-000000000000")


@override_settings(BACKGROUND_JOBS_ENABLED=True, FRONTEND_URL="https://i2g.example.edu")
class TicketSmsJobTests(TicketSmsTestCase):
    def setUp(self):
        super().setUp()
        self.turn_on()
        self.record = self.queue()

    def run_job(self):
        return process_claimed_job(claim_jobs()[0])

    def run_failing_job(self):
        with self.assertLogs("apps.core.services.background_jobs.worker", level="ERROR"):
            return self.run_job()

    @patch(SEND, return_value="msg-1")
    def test_the_text_carries_a_ticket_link_and_the_footer(self, send):
        self.assertTrue(self.run_job())

        self.record.refresh_from_db()
        self.assertEqual((self.record.status, self.record.message_id, self.record.attempts), ("sent", "msg-1", 1))
        destination, body = send.call_args.args
        self.assertEqual(destination, PHONE)
        self.assertEqual(send.call_args.kwargs["lane"], Lane.TRANSACTIONAL)
        self.assertTrue(body.startswith("Innovate to Grow: you're registered for Fall Demo. Your ticket: https://"))
        self.assertTrue(body.endswith("\nReply STOP to opt out."))
        link = SmsLinkToken.objects.get()
        # Personal sign-in links are off by default: the link opens the sign-in page, which returns to the ticket.
        self.assertIsNone(link.member)
        self.assertEqual(link.registration, self.registration)
        self.assertEqual(link.redirect_path, "/login?returnTo=/event-registration%3Fevent%3Dfall-demo")

    @patch(SEND, return_value="msg-1")
    def test_with_personal_links_on_it_signs_the_registrant_in(self, _send):
        sms_settings(personal_links_enabled=True)
        self.assertTrue(self.run_job())
        link = SmsLinkToken.objects.get()
        self.assertEqual((link.member, link.redirect_path), (self.member, "/event-registration?event=fall-demo"))

    @patch(SEND)
    def test_an_opted_out_number_is_never_texted(self, send):
        opt_out(PHONE)
        self.assertTrue(self.run_job())
        send.assert_not_called()
        self.record.refresh_from_db()
        self.assertEqual((self.record.status, self.record.error_message), ("opted_out", SKIPPED_MESSAGE))

    @patch(SEND)
    def test_quiet_hours_defer_the_job_to_their_end(self, send):
        with at(QUIET_MOMENT):
            self.assertFalse(self.run_job())
        send.assert_not_called()
        self.record.refresh_from_db()
        self.assertEqual((self.record.status, self.record.available_at), ("pending", QUIET_ENDS))
        self.assertEqual(self.record.error_message, HELD_LOG_MESSAGE)
        job = BackgroundJob.objects.get(kind="mail.ticket_sms")
        self.assertEqual((job.status, job.attempts), (BackgroundJob.Status.RETRY, 0))

    @patch(SEND)
    def test_turned_off_after_queueing_it_is_skipped(self, send):
        sms_settings(ticket_sms_enabled=False)
        self.assertTrue(self.run_job())
        send.assert_not_called()
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, "skipped")

    @patch(SEND, side_effect=SmsOptedOut(code="ConflictException", refused_by_provider=True))
    def test_aws_refusing_it_as_opted_out_revokes_the_link(self, _send):
        self.assertTrue(self.run_job())
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, "opted_out")
        self.assertLessEqual(SmsLinkToken.objects.get().expires_at, timezone.now())

    @patch(SEND, side_effect=SmsDeliveryError("SMS rejected the request.", outcome="permanent"))
    def test_a_permanent_refusal_fails_it_and_revokes_the_link(self, _send):
        self.assertFalse(self.run_failing_job())
        self.record.refresh_from_db()
        self.assertEqual((self.record.status, self.record.error_message), ("failed", "SMS rejected the request."))
        self.assertEqual(BackgroundJob.objects.get(kind="mail.ticket_sms").status, BackgroundJob.Status.FAILED)
        self.assertLessEqual(SmsLinkToken.objects.get().expires_at, timezone.now())

    @patch(SEND, side_effect=SmsDeliveryError("SMS temporarily rejected the request.", outcome="transient"))
    def test_a_temporary_failure_with_attempts_left_waits_for_the_retry(self, _send):
        self.assertFalse(self.run_failing_job())
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, "pending")
        self.assertEqual(self.record.error_message, "SMS temporarily rejected the request.")
        self.assertEqual(BackgroundJob.objects.get(kind="mail.ticket_sms").status, BackgroundJob.Status.RETRY)

    @patch(SEND, side_effect=SmsDeliveryError("SMS request outcome could not be confirmed.", outcome="uncertain"))
    def test_an_uncertain_send_keeps_the_link_it_may_have_delivered(self, _send):
        self.assertFalse(self.run_failing_job())
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, "uncertain")
        self.assertGreater(SmsLinkToken.objects.get().expires_at, timezone.now())
        self.assertEqual(BackgroundJob.objects.get(kind="mail.ticket_sms").status, BackgroundJob.Status.UNCERTAIN)

    @patch(SEND, return_value="msg-2")
    def test_a_finished_record_is_left_alone(self, send):
        TicketSms.objects.filter(pk=self.record.pk).update(status="sent")
        self.assertTrue(self.run_job())
        send.assert_not_called()
