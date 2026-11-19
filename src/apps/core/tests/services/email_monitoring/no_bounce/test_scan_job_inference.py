"""The scan job runs the no-bounce inference only after a scan that read the mailbox (ok or partial), and a failing
inference never breaks the chain of scans. End to end: a real scan of a fake Inbox confirms the bounced email's
failure and marks the quiet one "No bounce received"."""

from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

from apps.core.models import BackgroundJob, EmailMonitorState, OutboundEmail
from apps.core.services.email.bounces import BOUNCE_SCAN_JOB_KIND, ScanOutcome
from apps.core.services.email.bounces.scanning.jobs import run_scan_job

from ..bounce_scan.test_bounce_scanner import READER, FakeReader, _ScannerCase
from ..helpers import SENDER, GraphSendingMixin, make_email, monitoring_settings
from .test_quiet_inference import QuietCase

SCAN = "apps.core.services.email.bounces.scanning.scanner.scan_mailbox"
MARK = "apps.core.services.email.bounces.recording.quiet.mark_quiet_emails"
JOBS_LOGGER = "apps.core.services.email.bounces.jobs"
DeliveryStatus = OutboundEmail.DeliveryStatus


class ScanJobInferenceTests(QuietCase):
    def run_job(self, status: str) -> None:
        with patch(SCAN, return_value=ScanOutcome(status, SENDER)):
            run_scan_job(job=None)

    def test_a_scan_that_read_the_mailbox_marks_the_quiet_emails(self):
        for status in ("ok", "partial"):
            with self.subTest(status=status):
                email = self.email(hours_ago=72)
                self.run_job(status)
                self.assertEqual(self.status(email), DeliveryStatus.NO_BOUNCE)

    def test_any_other_outcome_marks_nothing(self):
        email = self.email(hours_ago=72)
        for status in ("failed", "busy", "locked", "paused", "disabled", "inactive"):
            with self.subTest(status=status):
                self.run_job(status)
                self.assertEqual(self.status(email), DeliveryStatus.UNKNOWN)

    def test_a_failing_inference_is_logged_without_details_and_the_next_scan_is_queued(self):
        with (
            patch(MARK, side_effect=RuntimeError("person@example.com")),
            self.assertLogs(JOBS_LOGGER, "ERROR") as logs,
        ):
            self.run_job("ok")

        self.assertEqual(BackgroundJob.objects.filter(kind=BOUNCE_SCAN_JOB_KIND).count(), 1)
        self.assertIn("RuntimeError", logs.output[0])
        self.assertNotIn("person@example.com", logs.output[0])

    def test_a_mailbox_without_state_marks_nothing(self):
        email = self.email(hours_ago=72)
        with patch(SCAN, return_value=ScanOutcome("ok", "other@ucmerced.edu")):
            run_scan_job(job=None)

        self.assertEqual(self.status(email), DeliveryStatus.UNKNOWN)


class EndToEndTests(GraphSendingMixin, _ScannerCase):
    def test_a_real_scan_confirms_the_bounce_and_marks_the_quiet_email(self):
        accepted = timezone.now() - timedelta(hours=72)
        quiet = make_email(
            mailbox=SENDER, recipient="quiet@example.com", accepted_at=accepted, last_attempt_at=accepted
        )
        recent = make_email(mailbox=SENDER, recipient="recent@example.com")
        reader = FakeReader(self.messages, self.bodies)

        with (
            patch(READER, return_value=(reader, SENDER, "")),
            monitoring_settings(bounce_initial_lookback_hours=24 * 7, no_bounce_after_hours=48),
        ):
            run_scan_job(job=None)

        for email, expected in (
            (self.email, DeliveryStatus.FAILURE_CONFIRMED),
            (quiet, DeliveryStatus.NO_BOUNCE),
            (recent, DeliveryStatus.UNKNOWN),
        ):
            email.refresh_from_db()
            self.assertEqual(email.delivery_status, expected)
        self.assertIsNotNone(EmailMonitorState.objects.get(mailbox=SENDER).scanned_since)
