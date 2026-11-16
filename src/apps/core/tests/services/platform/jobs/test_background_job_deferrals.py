"""The worker and the delivery limiter: deferred jobs keep their attempts, delivery jobs are claimed by priority,
and a paced or stopped lane is left unclaimed instead of being claimed and deferred job after job."""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.models import BackgroundJob
from apps.core.services import delivery_rates as rates
from apps.core.services.background_jobs import (
    DeferredJobError,
    JobOutcome,
    claim_jobs,
    enqueue_job,
    register_job_kind,
    registry,
    run_claimed_job,
)
from apps.core.services.background_jobs.registry import LANE_PRIORITIES, registered_job_kinds
from apps.core.services.delivery_rates.runtime import context
from apps.core.tests.services.delivery_rates.helpers import rates_with

MAILBOX = "i2g@example.edu"
BULK_KIND = "test.paced_campaign_send"
TRANSACTIONAL_KIND = "test.paced_login_code"
PLAIN_KIND = "test.unpaced_sheet_sync"
THIS = "apps.core.tests.services.platform.jobs.test_background_job_deferrals"


def active_graph_mailbox():
    return "graph_send", MAILBOX


def no_active_channel():
    return None


def paced_send_job(job):
    """A delivery handler as the email jobs are: admit on its lane, defer when the limiter says so."""
    lane = rates.Lane.BULK if job.kind == BULK_KIND else rates.Lane.TRANSACTIONAL
    try:
        admission = rates.admit("graph_send", MAILBOX, lane=lane, budget_cost=1, message_cost=1)
    except rates.RateDeferred as exc:
        raise DeferredJobError(str(exc), until=exc.until) from exc
    rates.record(admission, rates.ok())


def noop_job(job):
    return None


def register_test_kinds(test):
    """Register this module's job kinds for one test only (the registry is process-wide)."""
    patcher = patch.dict(registry._KINDS, clear=False)
    patcher.start()
    test.addCleanup(patcher.stop)
    register_job_kind(BULK_KIND, handler=f"{THIS}.paced_send_job", family="email", lane="bulk")
    register_job_kind(TRANSACTIONAL_KIND, handler=f"{THIS}.paced_send_job", family="email", lane="transactional")
    register_job_kind(PLAIN_KIND, handler=f"{THIS}.noop_job")


class RegisteredKindsTestCase(TestCase):
    def setUp(self):
        super().setUp()
        register_test_kinds(self)


class JobKindRegistrationTests(RegisteredKindsTestCase):
    def test_delivery_kinds_carry_their_lane_and_priority(self):
        kinds = registered_job_kinds()

        for name in ("event.ticket_email", "authn.notification_email"):
            with self.subTest(name):
                kind = kinds[name]
                self.assertEqual((kind.family, kind.lane, kind.priority), ("email", "transactional", 10))
        self.assertEqual((kinds["mail.email_recipient"].family, kinds["mail.email_recipient"].priority), ("email", 100))
        self.assertEqual((kinds["mail.sms_recipient"].family, kinds["mail.sms_recipient"].lane), ("sms", "bulk"))
        self.assertEqual((kinds["cms.amplify_redirects"].family, kinds["cms.amplify_redirects"].priority), (None, 50))

    def test_a_queued_job_takes_its_kinds_priority(self):
        bulk, _ = enqueue_job(kind=BULK_KIND, dedupe_key="a", payload={})
        login, _ = enqueue_job(kind=TRANSACTIONAL_KIND, dedupe_key="a", payload={})
        plain, _ = enqueue_job(kind="test.never_registered", dedupe_key="a", payload={})

        self.assertEqual((bulk.priority, login.priority, plain.priority), (LANE_PRIORITIES["bulk"], 10, 50))
        self.assertEqual(bulk.max_attempts, 5)

    def test_a_family_without_a_lane_is_refused(self):
        from django.core.exceptions import ImproperlyConfigured

        with self.assertRaises(ImproperlyConfigured):
            register_job_kind("test.half_declared", handler=f"{THIS}.noop_job", family="email")
        with self.assertRaises(ImproperlyConfigured):
            register_job_kind("test.wrong_lane", handler=f"{THIS}.noop_job", family="email", lane="fast")


class DeferredJobTests(RegisteredKindsTestCase):
    def deferred_job(self, *, max_attempts=1, started=False):
        job, _ = enqueue_job(kind=PLAIN_KIND, dedupe_key="deferred", payload={}, max_attempts=max_attempts)
        job = claim_jobs()[0]
        if started:
            job.begin_provider_call()
        return job

    def test_a_deferral_keeps_the_attempt_and_never_fails_the_job(self):
        until = timezone.now() + timedelta(seconds=40)
        for _round in range(3):
            job = self.deferred_job()
            with patch(
                "apps.core.services.background_jobs.worker.get_handler",
                return_value=lambda _job: (_ for _ in ()).throw(DeferredJobError(until=until)),
            ):
                self.assertEqual(run_claimed_job(job), JobOutcome.DEFERRED)
            job.refresh_from_db()
            self.assertEqual((job.status, job.attempts), (BackgroundJob.Status.RETRY, 0))
            self.assertGreaterEqual(job.available_at, until)
            self.assertLessEqual(job.available_at, until + timedelta(seconds=1))
            BackgroundJob.objects.filter(pk=job.pk).update(available_at=timezone.now())

    def test_a_deferral_wrapped_in_another_error_still_counts(self):
        job = self.deferred_job()

        def handler(_job):
            try:
                raise DeferredJobError(until=timezone.now() + timedelta(seconds=5))
            except DeferredJobError as exc:
                raise RuntimeError("Ticket email delivery provider failed.") from exc

        with patch("apps.core.services.background_jobs.worker.get_handler", return_value=handler):
            self.assertEqual(run_claimed_job(job), JobOutcome.DEFERRED)

    def test_after_the_provider_call_began_a_deferral_is_an_ordinary_failure(self):
        job = self.deferred_job(started=True)

        def handler(_job):
            raise DeferredJobError(until=timezone.now() + timedelta(seconds=5))

        with patch("apps.core.services.background_jobs.worker.get_handler", return_value=handler):
            self.assertEqual(run_claimed_job(job), JobOutcome.FAILED)
        job.refresh_from_db()
        self.assertEqual((job.status, job.attempts), (BackgroundJob.Status.FAILED, 1))

    def test_handlers_run_in_the_worker_wait_mode(self):
        job = self.deferred_job()
        seen = []
        with patch(
            "apps.core.services.background_jobs.worker.get_handler",
            return_value=lambda _job: seen.append(context.current_wait_mode()),
        ):
            run_claimed_job(job)

        self.assertEqual(seen, [rates.WaitMode.WORKER])

    def test_retry_backoff_comes_from_the_settings(self):
        job = self.deferred_job(max_attempts=3)
        with (
            override_settings(DELIVERY_RATES=rates_with(jobs={"retry_base_seconds": 40})),
            patch(
                "apps.core.services.background_jobs.worker.get_handler",
                return_value=lambda _job: (_ for _ in ()).throw(ConnectionError("down")),
            ),
        ):
            before = timezone.now()
            self.assertEqual(run_claimed_job(job), JobOutcome.FAILED)
        job.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.RETRY)
        self.assertGreaterEqual(job.available_at, before + timedelta(seconds=40))
