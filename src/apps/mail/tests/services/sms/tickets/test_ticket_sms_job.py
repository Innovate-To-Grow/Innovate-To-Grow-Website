from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone

from apps.core.models import BackgroundJob
from apps.core.services.aws.sms_errors import SmsDeliveryError, SmsOptedOut
from apps.core.services.background_jobs import claim_jobs, process_claimed_job
from apps.core.services.delivery_rates import Lane
from apps.mail.models import SmsLinkToken, TicketSms
from apps.mail.services.sms.policy.opt_outs import SKIPPED_MESSAGE
from apps.mail.services.sms.policy.quiet_hours import HELD_LOG_MESSAGE
from apps.mail.tests.services.sms.tickets.test_ticket_sms import PHONE, SEND, TicketSmsTestCase

from ..policy.policy_helpers import QUIET_ENDS, QUIET_MOMENT, at, opt_out, sms_settings


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

    @patch(SEND, return_value="msg-1")
    def test_a_phone_verified_only_for_the_registration_never_gets_a_personal_link(self, _send):
        # It may be someone else's phone (a family or lab phone): the link opens the sign-in page instead.
        sms_settings(personal_links_enabled=True)
        TicketSms.objects.filter(pk=self.record.pk).update(phone_number="+12095550199")
        self.assertTrue(self.run_job())
        link = SmsLinkToken.objects.get()
        self.assertIsNone(link.member)
        self.assertTrue(link.redirect_path.startswith("/login?returnTo="))

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
