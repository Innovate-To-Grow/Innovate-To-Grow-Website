"""Delivery outcomes in the core queue: Retry-After hints, limiter deferrals and the retry schedule."""

from datetime import timedelta
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.core.models import BackgroundJob
from apps.core.services.aws.provider_outcomes import ProviderDeliveryError
from apps.core.services.background_jobs import (
    DeferredJobError,
    PermanentJobError,
    TransientJobError,
    UncertainJobError,
    claim_jobs,
    enqueue_job,
    process_claimed_job,
)
from apps.core.services.background_jobs.delivery import provider_job_error
from apps.core.services.background_jobs.worker import _retry_delay
from apps.core.services.delivery_rates import RateDeferred
from apps.core.services.email import (
    PermanentEmailDeliveryError,
    TransientEmailDeliveryError,
    UncertainEmailDeliveryError,
)
from apps.core.services.email.exceptions import EmailRateDeferred


class DeliveryErrorRetryAfterTest(SimpleTestCase):
    def test_transient_errors_carry_the_hint_and_default_to_none(self):
        self.assertIsNone(TransientEmailDeliveryError("busy").retry_after)
        self.assertEqual(TransientEmailDeliveryError("busy", retry_after=12.0).retry_after, 12.0)

    def test_other_outcomes_have_no_hint(self):
        for error in (PermanentEmailDeliveryError("no"), UncertainEmailDeliveryError("maybe")):
            with self.subTest(type(error).__name__):
                self.assertIsNone(error.retry_after)

    def test_the_provider_job_error_keeps_the_hint(self):
        job_error = provider_job_error(TransientEmailDeliveryError("busy", retry_after=30.0))

        self.assertIsInstance(job_error, TransientJobError)
        self.assertEqual(job_error.retry_after, 30.0)
        self.assertEqual(str(job_error), "busy")

    def test_a_transient_error_without_a_hint_maps_to_no_hint(self):
        self.assertIsNone(provider_job_error(TransientEmailDeliveryError("busy")).retry_after)

    def test_errors_from_other_providers_map_without_a_hint_attribute(self):
        error = ProviderDeliveryError("busy", outcome="transient")
        del error.retry_after

        self.assertIsNone(provider_job_error(error).retry_after)

    def test_a_limiter_deferral_becomes_a_deferred_job_even_when_wrapped(self):
        now = timezone.now()
        deferred = EmailRateDeferred(RateDeferred(now + timedelta(seconds=42), "pace", now=now))
        try:
            raise ProviderDeliveryError(str(deferred), outcome=deferred.outcome) from deferred
        except ProviderDeliveryError as wrapped:
            for error in (deferred, wrapped):
                with self.subTest(type(error).__name__):
                    job_error = provider_job_error(error)

                    self.assertIsInstance(job_error, DeferredJobError)
                    self.assertEqual(job_error.until, deferred.until)
        self.assertEqual(deferred.retry_after, 42)
        self.assertEqual(str(deferred), "Email delivery is busy right now; try again in about 42 seconds.")

    def test_permanent_and_uncertain_outcomes_are_unchanged(self):
        self.assertIsInstance(provider_job_error(PermanentEmailDeliveryError("no")), PermanentJobError)
        self.assertIsInstance(provider_job_error(UncertainEmailDeliveryError("maybe")), UncertainJobError)


class RetryDelayTest(SimpleTestCase):
    def test_backoff_doubles_from_fifteen_seconds_up_to_an_hour(self):
        chain = (TransientJobError("x"),)
        self.assertEqual([_retry_delay(n, chain) for n in (1, 2, 3, 4, 5)], [15, 30, 60, 120, 240])
        self.assertEqual(_retry_delay(30, chain), 3600)

    def test_a_longer_hint_stretches_the_delay(self):
        self.assertEqual(_retry_delay(1, (TransientJobError("x", retry_after=120.0),)), 120)

    def test_a_shorter_hint_never_shortens_the_backoff(self):
        self.assertEqual(_retry_delay(3, (TransientJobError("x", retry_after=5.0),)), 60)

    def test_fractional_hints_round_up(self):
        self.assertEqual(_retry_delay(1, (TransientJobError("x", retry_after=20.2),)), 21)

    def test_hints_are_capped_at_an_hour(self):
        self.assertEqual(_retry_delay(1, (TransientJobError("x", retry_after=99999.0),)), 3600)

    def test_the_largest_hint_in_the_chain_wins_and_other_errors_are_ignored(self):
        chain = (
            RuntimeError("wrapper"),
            TransientJobError("a", retry_after=40.0),
            TransientJobError("b", retry_after=90.0),
            TransientJobError("c"),
        )
        self.assertEqual(_retry_delay(1, chain), 90)

    def test_no_hint_means_plain_backoff(self):
        self.assertEqual(_retry_delay(2, (RuntimeError("x"),)), 30)


class JobRetryScheduleTest(TestCase):
    def run_failing_job(self, error):
        def fail(_job):
            raise error

        with patch("apps.core.services.background_jobs.worker.get_handler", return_value=fail):
            job, _created = enqueue_job(kind="test.echo", dedupe_key="retry-after", payload={})
            before = timezone.now()
            self.assertFalse(process_claimed_job(claim_jobs()[0]))
        job.refresh_from_db()
        return job, before

    def test_a_retry_after_hint_postpones_the_next_attempt(self):
        job, before = self.run_failing_job(TransientJobError("throttled", retry_after=600.0))

        self.assertEqual(job.status, BackgroundJob.Status.RETRY)
        self.assertGreaterEqual(job.available_at, before + timedelta(seconds=600))
        self.assertLess(job.available_at, before + timedelta(seconds=660))

    def test_without_a_hint_the_first_retry_is_fifteen_seconds_out(self):
        job, before = self.run_failing_job(TransientJobError("throttled"))

        self.assertEqual(job.status, BackgroundJob.Status.RETRY)
        self.assertGreaterEqual(job.available_at, before + timedelta(seconds=15))
        self.assertLess(job.available_at, before + timedelta(seconds=45))

    def test_a_hint_on_a_wrapped_error_is_found_through_the_cause_chain(self):
        try:
            try:
                raise TransientJobError("throttled", retry_after=300.0)
            except TransientJobError as cause:
                raise RuntimeError("handler failed") from cause
        except RuntimeError as wrapped:
            job, before = self.run_failing_job(wrapped)

        self.assertEqual(job.status, BackgroundJob.Status.RETRY)
        self.assertGreaterEqual(job.available_at, before + timedelta(seconds=300))

    def test_known_transient_errors_without_a_hint_keep_the_plain_backoff(self):
        job, before = self.run_failing_job(TimeoutError("socket"))

        self.assertEqual(job.status, BackgroundJob.Status.RETRY)
        self.assertLess(job.available_at, before + timedelta(seconds=45))
