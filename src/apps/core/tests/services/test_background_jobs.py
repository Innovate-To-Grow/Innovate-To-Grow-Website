import json
from datetime import timedelta
from unittest.mock import patch

import boto3
from botocore.stub import Stubber
from django.db import OperationalError
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from gspread.exceptions import APIError as GspreadAPIError
from requests import Response

from apps.core.models import BackgroundJob
from apps.core.services.background_jobs import (
    PermanentJobError,
    TransientJobError,
    claim_jobs,
    enqueue_job,
    process_claimed_job,
    recover_stale_jobs,
    retry_job,
    worker_metrics,
)
from apps.core.services.background_jobs.metrics import publish_worker_metrics


def _gspread_api_error(status_code: int) -> GspreadAPIError:
    response = Response()
    response.status_code = status_code
    response._content = json.dumps(  # noqa: SLF001 - build the response gspread expects.
        {
            "error": {
                "code": status_code,
                "message": "Google Sheets request failed",
                "status": "UNAVAILABLE",
            }
        }
    ).encode()
    return GspreadAPIError(response)


class BackgroundJobQueueTests(TestCase):
    def test_enqueue_is_idempotent_by_kind_and_dedupe_key(self):
        first, created = enqueue_job(
            kind="test.echo",
            dedupe_key="same",
            payload={"value": 1},
        )
        second, created_again = enqueue_job(
            kind="test.echo",
            dedupe_key="same",
            payload={"value": 2},
        )

        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(second.payload, {"value": 1})

    def test_claim_sets_token_attempt_and_processing_state(self):
        job, _created = enqueue_job(kind="test.echo", dedupe_key="claim", payload={})

        claimed = claim_jobs(batch_size=5)

        self.assertEqual([item.pk for item in claimed], [job.pk])
        claimed_job = claimed[0]
        self.assertEqual(claimed_job.status, BackgroundJob.Status.PROCESSING)
        self.assertEqual(claimed_job.attempts, 1)
        self.assertIsNotNone(claimed_job.claim_token)
        self.assertIsNotNone(claimed_job.claimed_at)
        self.assertEqual(claim_jobs(batch_size=5), [])

    @patch("apps.core.services.background_jobs.worker.get_handler")
    def test_successful_job_completes(self, get_handler):
        get_handler.return_value = lambda _job: None
        job, _created = enqueue_job(kind="test.echo", dedupe_key="success", payload={})
        claimed = claim_jobs()[0]

        self.assertTrue(process_claimed_job(claimed))

        job.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.SUCCEEDED)
        self.assertIsNotNone(job.completed_at)
        self.assertIsNone(job.claim_token)

    @patch(
        "apps.core.services.background_jobs.worker.notify_job_state",
        side_effect=RuntimeError("mirror unavailable"),
    )
    @patch("apps.core.services.background_jobs.worker.get_handler")
    def test_state_mirror_failure_does_not_escape_job_boundary(self, get_handler, _notify):
        get_handler.return_value = lambda _job: None
        job, _created = enqueue_job(kind="test.echo", dedupe_key="mirror", payload={})

        self.assertTrue(process_claimed_job(claim_jobs()[0]))

        job.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.SUCCEEDED)

    @patch("apps.core.services.background_jobs.worker.get_handler")
    def test_known_transient_failure_uses_exponential_retry(self, get_handler):
        def fail(_job):
            raise TransientJobError("temporary")

        get_handler.return_value = fail
        job, _created = enqueue_job(kind="test.echo", dedupe_key="retry", payload={})
        claimed = claim_jobs()[0]

        self.assertFalse(process_claimed_job(claimed))

        job.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.RETRY)
        self.assertGreater(job.available_at, timezone.now())
        self.assertEqual(job.last_error, "temporary")

    @patch("apps.core.services.background_jobs.worker.get_handler")
    def test_transient_gspread_http_statuses_retry(self, get_handler):
        for status_code in (408, 429, 500, 503, 599):
            with self.subTest(status_code=status_code):
                get_handler.return_value = lambda _job, status=status_code: (_ for _ in ()).throw(
                    _gspread_api_error(status)
                )
                job, _created = enqueue_job(
                    kind="test.sheet",
                    dedupe_key=f"gspread-{status_code}",
                    payload={},
                )

                self.assertFalse(process_claimed_job(claim_jobs(batch_size=1)[0]))

                job.refresh_from_db()
                self.assertEqual(job.status, BackgroundJob.Status.RETRY)

    @patch("apps.core.services.background_jobs.worker.get_handler")
    def test_permanent_gspread_http_status_fails(self, get_handler):
        get_handler.return_value = lambda _job: (_ for _ in ()).throw(_gspread_api_error(400))
        job, _created = enqueue_job(
            kind="test.sheet",
            dedupe_key="gspread-400",
            payload={},
        )

        self.assertFalse(process_claimed_job(claim_jobs()[0]))

        job.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.FAILED)

    @patch(
        "apps.core.services.background_jobs.worker.notify_job_state",
        side_effect=RuntimeError("mirror unavailable"),
    )
    @patch("apps.core.services.background_jobs.worker.get_handler")
    def test_failed_state_mirror_does_not_escape_job_boundary(self, get_handler, _notify):
        get_handler.return_value = lambda _job: (_ for _ in ()).throw(TransientJobError("temporary"))
        job, _created = enqueue_job(kind="test.echo", dedupe_key="failed-mirror", payload={})

        self.assertFalse(process_claimed_job(claim_jobs()[0]))

        job.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.RETRY)

    @patch("apps.core.services.background_jobs.worker.get_handler")
    def test_provider_failure_is_uncertain_and_not_automatically_retried(self, get_handler):
        def fail(job):
            job.begin_provider_call()
            raise TimeoutError("provider timeout")

        get_handler.return_value = fail
        job, _created = enqueue_job(
            kind="test.delivery",
            dedupe_key="uncertain",
            payload={},
            can_retry_after_claim=False,
        )
        claimed = claim_jobs()[0]

        self.assertFalse(process_claimed_job(claimed))

        job.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.UNCERTAIN)
        self.assertIsNotNone(job.completed_at)
        self.assertTrue(retry_job(job))
        job.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.RETRY)

    @patch(
        "apps.core.services.background_jobs.registry.notify_job_state",
        side_effect=OperationalError("domain mirror unavailable"),
    )
    def test_manual_retry_rolls_back_if_domain_mirror_fails(self, _notify):
        job, _created = enqueue_job(
            kind="test.delivery",
            dedupe_key="atomic-manual-retry",
            payload={},
        )
        completed_at = timezone.now()
        BackgroundJob.objects.filter(pk=job.pk).update(
            status=BackgroundJob.Status.UNCERTAIN,
            completed_at=completed_at,
            last_error="Review delivery",
        )
        job.refresh_from_db()

        with self.assertRaisesMessage(OperationalError, "domain mirror unavailable"):
            retry_job(job)

        job.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.UNCERTAIN)
        self.assertEqual(job.completed_at, completed_at)
        self.assertEqual(job.last_error, "Review delivery")
        self.assertEqual(claim_jobs(), [])

    @patch("apps.core.services.background_jobs.worker.get_handler")
    def test_definitive_transient_provider_rejection_retries_after_call_started(self, get_handler):
        def fail(job):
            job.begin_provider_call()
            raise TransientJobError("provider throttled")

        get_handler.return_value = fail
        job, _created = enqueue_job(
            kind="test.delivery",
            dedupe_key="definitive-transient",
            payload={},
            can_retry_after_claim=False,
        )

        self.assertFalse(process_claimed_job(claim_jobs()[0]))

        job.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.RETRY)

    @patch("apps.core.services.background_jobs.worker.get_handler")
    def test_definitive_permanent_provider_rejection_fails_not_uncertain(self, get_handler):
        def fail(job):
            job.begin_provider_call()
            raise PermanentJobError("access denied")

        get_handler.return_value = fail
        job, _created = enqueue_job(
            kind="test.delivery",
            dedupe_key="definitive-permanent",
            payload={},
            can_retry_after_claim=False,
        )

        self.assertFalse(process_claimed_job(claim_jobs()[0]))

        job.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.FAILED)

    def test_stale_recovery_retries_safe_jobs_and_quarantines_deliveries(self):
        stale_at = timezone.now() - timedelta(hours=1)
        safe, _created = enqueue_job(
            kind="test.safe",
            dedupe_key="safe",
            payload={},
            can_retry_after_claim=True,
        )
        delivery, _created = enqueue_job(
            kind="test.delivery",
            dedupe_key="delivery",
            payload={},
            can_retry_after_claim=False,
        )
        BackgroundJob.objects.filter(pk=safe.pk).update(
            status=BackgroundJob.Status.PROCESSING,
            claimed_at=stale_at,
            claim_token=BackgroundJob.new_claim_token(),
        )
        BackgroundJob.objects.filter(pk=delivery.pk).update(
            status=BackgroundJob.Status.PROCESSING,
            claimed_at=stale_at,
            claim_token=BackgroundJob.new_claim_token(),
            provider_call_started_at=stale_at,
        )

        result = recover_stale_jobs(stale_after=timedelta(minutes=10))

        self.assertEqual(result, {"completed": 0, "retried": 1, "failed": 0, "uncertain": 1})
        safe.refresh_from_db()
        delivery.refresh_from_db()
        self.assertEqual(safe.status, BackgroundJob.Status.RETRY)
        self.assertEqual(delivery.status, BackgroundJob.Status.UNCERTAIN)

    def test_stale_recovery_fails_job_at_max_attempts(self):
        stale_at = timezone.now() - timedelta(hours=1)
        job, _created = enqueue_job(
            kind="test.safe",
            dedupe_key="exhausted-stale-job",
            payload={},
            max_attempts=1,
        )
        claimed = claim_jobs()[0]
        BackgroundJob.objects.filter(pk=claimed.pk).update(claimed_at=stale_at)

        result = recover_stale_jobs(stale_after=timedelta(minutes=10))

        job.refresh_from_db()
        self.assertEqual(result, {"completed": 0, "retried": 0, "failed": 1, "uncertain": 0})
        self.assertEqual(job.status, BackgroundJob.Status.FAILED)
        self.assertIsNotNone(job.completed_at)
        self.assertIn("Maximum attempts", job.last_error)
        self.assertEqual(claim_jobs(), [])

    def test_recovery_mirror_failure_rolls_back_one_job_without_blocking_next(self):
        stale_at = timezone.now() - timedelta(hours=1)
        broken, _created = enqueue_job(
            kind="test.safe",
            dedupe_key="broken-recovery-mirror",
            payload={},
        )
        healthy, _created = enqueue_job(
            kind="test.safe",
            dedupe_key="healthy-recovery-mirror",
            payload={},
        )
        BackgroundJob.objects.filter(pk__in=[broken.pk, healthy.pk]).update(
            status=BackgroundJob.Status.PROCESSING,
            claimed_at=stale_at,
            claim_token=BackgroundJob.new_claim_token(),
        )

        def mirror(job):
            if job.pk == broken.pk:
                raise OperationalError("mirror database unavailable")

        with patch(
            "apps.core.services.background_jobs.recovery.notify_job_state",
            side_effect=mirror,
        ):
            result = recover_stale_jobs(stale_after=timedelta(minutes=10))

        broken.refresh_from_db()
        healthy.refresh_from_db()
        self.assertEqual(result, {"completed": 0, "retried": 1, "failed": 0, "uncertain": 0})
        self.assertEqual(broken.status, BackgroundJob.Status.PROCESSING)
        self.assertIsNotNone(broken.claim_token)
        self.assertEqual(healthy.status, BackgroundJob.Status.RETRY)
        self.assertIsNone(healthy.claim_token)

    def test_metrics_report_queue_and_terminal_counts(self):
        enqueue_job(kind="test.echo", dedupe_key="pending", payload={})
        failed, _created = enqueue_job(kind="test.echo", dedupe_key="failed", payload={})
        uncertain, _created = enqueue_job(kind="test.echo", dedupe_key="uncertain-metric", payload={})
        BackgroundJob.objects.filter(pk=failed.pk).update(status=BackgroundJob.Status.FAILED)
        BackgroundJob.objects.filter(pk=uncertain.pk).update(status=BackgroundJob.Status.UNCERTAIN)

        metrics = worker_metrics()

        self.assertEqual(metrics["heartbeat"], 1)
        self.assertEqual(metrics["queue_depth"], 1)
        self.assertEqual(metrics["failed_jobs"], 1)
        self.assertEqual(metrics["uncertain_jobs"], 1)


# publish_worker_metrics against a real CloudWatch client and botocore's Stubber: the Stubber validates each
# request against the service model botocore ships, so an upgrade that changes PutMetricData fails here.
METRICS_REGION = "us-west-2"
METRICS_CLIENT = "boto3.client"  # imported inside the function, so patch the attribute it reads
METRICS = {"heartbeat": 1, "queue_depth": 3, "oldest_job_age_seconds": 12.5, "failed_jobs": 0, "uncertain_jobs": 2}


def stubbed_cloudwatch():
    client = boto3.client(
        "cloudwatch",
        region_name=METRICS_REGION,
        aws_access_key_id="test-access-key",
        aws_secret_access_key="test-secret-key",
    )
    return client, Stubber(client)


@override_settings(BACKGROUND_JOB_METRICS_NAMESPACE="I2G/Workers", AWS_S3_REGION_NAME=METRICS_REGION)
class PublishWorkerMetricsTests(SimpleTestCase):
    def test_puts_every_metric_with_its_unit_in_the_namespace(self):
        client, stubber = stubbed_cloudwatch()
        stubber.add_response(
            "put_metric_data",
            {},
            {
                "Namespace": "I2G/Workers",
                "MetricData": [
                    {"MetricName": "WorkerHeartbeat", "Value": 1.0, "Unit": "Count"},
                    {"MetricName": "QueueDepth", "Value": 3.0, "Unit": "Count"},
                    {"MetricName": "OldestJobAge", "Value": 12.5, "Unit": "Seconds"},
                    {"MetricName": "FailedJobs", "Value": 0.0, "Unit": "Count"},
                    {"MetricName": "UncertainJobs", "Value": 2.0, "Unit": "Count"},
                ],
            },
        )

        with stubber, patch(METRICS_CLIENT, return_value=client) as factory:
            publish_worker_metrics(METRICS)

        stubber.assert_no_pending_responses()
        factory.assert_called_once_with("cloudwatch", region_name=METRICS_REGION)

    def test_provider_error_is_logged_not_raised(self):
        client, stubber = stubbed_cloudwatch()
        stubber.add_client_error("put_metric_data", service_error_code="Throttling", http_status_code=400)

        with (
            stubber,
            patch(METRICS_CLIENT, return_value=client),
            self.assertLogs("apps.core.services.background_jobs.metrics", level="ERROR") as logs,
        ):
            publish_worker_metrics(METRICS)

        self.assertIn("Could not publish background worker metrics", logs.output[0])

    @override_settings(BACKGROUND_JOB_METRICS_NAMESPACE="")
    def test_no_namespace_means_no_client(self):
        with patch(METRICS_CLIENT) as factory:
            publish_worker_metrics(METRICS)

        factory.assert_not_called()
