import json
from unittest.mock import patch

import boto3
from botocore.stub import Stubber
from django.test import TestCase
from django.utils import timezone
from gspread.exceptions import APIError as GspreadAPIError
from requests import Response

from apps.core.models import BackgroundJob
from apps.core.services.background_jobs import (
    TransientJobError,
    claim_jobs,
    enqueue_job,
    process_claimed_job,
)


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
