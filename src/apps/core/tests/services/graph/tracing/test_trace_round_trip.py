"""The Message Trace sync end to end: the worker runs the job, the real reader pages through Microsoft's trace (faked
behind ``graph.transport.request``), the statuses are written and the next sync is queued; and the job's scheduling."""

from datetime import timedelta
from unittest.mock import patch
from urllib.parse import unquote

from django.test import TestCase
from django.utils import timezone

from apps.core.models import BackgroundJob, EmailDeliveryTraceState, MicrosoftGraphProviderConfig, OutboundEmail
from apps.core.services.background_jobs import claim_jobs, run_claimed_job
from apps.core.services.background_jobs.registry import registered_job_kinds
from apps.core.services.email.graph import transport
from apps.core.services.email.graph.tracing import DELIVERY_TRACE_JOB_KIND, TraceOutcome, ensure_scheduled, run_now
from apps.core.services.email.graph.tracing.jobs import next_delay, purge_finished_jobs, run_trace_job

from . import SENDER, TraceSetupMixin, trace_page, trace_row

DeliveryStatus = OutboundEmail.DeliveryStatus
SYNC = "apps.core.services.email.graph.tracing.jobs.sync_delivery"


def trace_jobs():
    return BackgroundJob.objects.filter(kind=DELIVERY_TRACE_JOB_KIND)


class RoundTripTests(TraceSetupMixin, TestCase):
    def test_the_worker_syncs_through_the_real_reader_and_queues_the_next_sync(self):
        mime = self.sent(recipients=["a@example.com", "b@example.com"], recipient="a@example.com", recipient_count=2)
        json_sent = self.sent(hours_ago=1.5, internet_message_id="", subject="Your code")
        self.microsoft.pages = [
            trace_page(
                [
                    trace_row(recipient="a@example.com", received=mime.accepted_at),
                    trace_row(recipient="b@example.com", status="quarantined", received=mime.accepted_at),
                ],
                skiptoken="page~2",
            ),
            trace_page([trace_row("<json@namprd.outlook.com>", subject="Your code", received=json_sent.accepted_at)]),
        ]

        self.assertTrue(run_now())
        for job in claim_jobs():
            run_claimed_job(job)

        mime.refresh_from_db()
        json_sent.refresh_from_db()
        self.assertEqual((mime.delivery_status, mime.trace_status), (DeliveryStatus.QUARANTINED, "quarantined"))
        self.assertEqual(json_sent.delivery_status, DeliveryStatus.DELIVERED)
        traces = self.microsoft.traces
        self.assertEqual([request["method"] for request in traces], ["GET", "GET"])
        for request in traces:
            self.assertTrue(transport.is_allowed("GET", transport.GRAPH_HOST, request["path"]))
            self.assertIn(f"senderAddress eq '{SENDER}'", unquote(request["path"]))
        self.assertTrue(traces[1]["path"].endswith("&$skiptoken=page%7E2"))
        state = EmailDeliveryTraceState.objects.get(sender=SENDER)
        self.assertEqual((state.permission, state.last_run_stats["requests"]), ("ok", 2))
        self.assertEqual(trace_jobs().filter(status=BackgroundJob.Status.SUCCEEDED).count(), 1)
        following = trace_jobs().get(status=BackgroundJob.Status.PENDING)
        self.assertAlmostEqual((following.available_at - timezone.now()).total_seconds(), 1800, delta=10)

    def test_the_job_kind_is_registered_by_the_core_app(self):
        self.assertIn(DELIVERY_TRACE_JOB_KIND, registered_job_kinds())


class SchedulingTests(TraceSetupMixin, TestCase):
    def test_maintenance_queues_one_sync_only_while_message_trace_is_on(self):
        self.assertTrue(ensure_scheduled())
        self.assertFalse(ensure_scheduled())
        self.assertEqual(trace_jobs().get().max_attempts, 1)

        trace_jobs().delete()
        MicrosoftGraphProviderConfig.objects.update(message_trace_enabled=False)
        self.assertFalse(ensure_scheduled())
        self.assertFalse(run_now())
        self.assertFalse(trace_jobs().exists())

    def test_sync_now_pulls_the_waiting_sync_forward_and_never_queues_a_second(self):
        ensure_scheduled(now=timezone.now() + timedelta(minutes=20))

        self.assertTrue(run_now())
        self.assertTrue(run_now())

        self.assertLessEqual(trace_jobs().get().available_at, timezone.now())

    def test_sync_now_does_nothing_while_a_sync_runs(self):
        ensure_scheduled()
        trace_jobs().update(status=BackgroundJob.Status.PROCESSING)

        self.assertFalse(run_now())
        self.assertEqual(trace_jobs().count(), 1)

    def test_the_chain_follows_the_backoff_and_ends_when_switched_off(self):
        with patch(SYNC, return_value=TraceOutcome("not_permitted", retry_after=6 * 3600)):
            run_trace_job(job=None)
        job = trace_jobs().get()
        self.assertAlmostEqual((job.available_at - timezone.now()).total_seconds(), 6 * 3600, delta=10)

        trace_jobs().delete()
        MicrosoftGraphProviderConfig.objects.update(message_trace_enabled=False)
        with patch(SYNC, side_effect=RuntimeError("database gone")), self.assertRaises(RuntimeError):
            run_trace_job(job=None)
        self.assertFalse(trace_jobs().exists())

    def test_next_delay_is_the_interval_or_the_longer_backoff(self):
        self.assertEqual(next_delay(None), 1800)
        self.assertEqual(next_delay(TraceOutcome("busy", retry_after=300)), 1800)
        self.assertEqual(next_delay(TraceOutcome("busy", retry_after=3600)), 3600)

    def test_finished_sync_jobs_older_than_a_week_are_purged(self):
        now = timezone.now()
        for days, status in ((8, "succeeded"), (8, "failed"), (2, "succeeded"), (8, "pending")):
            completed = now - timedelta(days=days)
            BackgroundJob.objects.create(
                kind=DELIVERY_TRACE_JOB_KIND, dedupe_key=f"{days}{status}", status=status, completed_at=completed
            )

        self.assertEqual(purge_finished_jobs(now=now), 2)
        self.assertEqual(trace_jobs().count(), 2)
