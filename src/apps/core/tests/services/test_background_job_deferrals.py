"""The worker and the delivery limiter: deferred jobs keep their attempts, delivery jobs are claimed by priority,
and a paced or stopped lane is left unclaimed instead of being claimed and deferred job after job."""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.models import BackgroundJob, DeliveryRateState
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
from apps.core.services.background_jobs.gating import blocked_job_kinds
from apps.core.services.background_jobs.registry import LANE_PRIORITIES, registered_job_kinds
from apps.core.services.delivery_rates import families
from apps.core.services.delivery_rates.runtime import context
from apps.core.tests.services.delivery_rates.helpers import FakeClock, rates_with

MAILBOX = "i2g@example.edu"
BULK_KIND = "test.paced_campaign_send"
TRANSACTIONAL_KIND = "test.paced_login_code"
PLAIN_KIND = "test.unpaced_sheet_sync"
THIS = "apps.core.tests.services.test_background_job_deferrals"


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


class ClaimOrderTests(RegisteredKindsTestCase):
    def test_a_login_code_queued_after_many_due_campaign_jobs_is_claimed_first(self):
        now = timezone.now()
        BackgroundJob.objects.bulk_create(
            BackgroundJob(kind=BULK_KIND, dedupe_key=str(index), priority=100, available_at=now - timedelta(hours=1))
            for index in range(1000)
        )
        enqueue_job(kind=TRANSACTIONAL_KIND, dedupe_key="code", payload={})

        self.assertEqual(claim_jobs(batch_size=1)[0].kind, TRANSACTIONAL_KIND)

    def test_equal_priorities_keep_the_longest_due_first(self):
        now = timezone.now()
        later, _ = enqueue_job(kind=PLAIN_KIND, dedupe_key="later", payload={}, available_at=now - timedelta(minutes=1))
        earlier, _ = enqueue_job(
            kind=PLAIN_KIND, dedupe_key="early", payload={}, available_at=now - timedelta(minutes=5)
        )

        self.assertEqual([job.pk for job in claim_jobs(batch_size=2)], [earlier.pk, later.pk])


@patch.dict(families._RESOLVERS, {rates.Family.EMAIL: f"{THIS}.active_graph_mailbox"})
@override_settings(DELIVERY_RATES=rates_with(jobs={"gate_cache_seconds": 1e-6}))
class LaneGateTests(RegisteredKindsTestCase):
    def setUp(self):
        super().setUp()
        families.clear_gate_cache()
        self.addCleanup(families.clear_gate_cache)
        self.now = timezone.now()

    def gate(self, **gates):
        DeliveryRateState.objects.update_or_create(
            channel="graph_send", identity=MAILBOX, defaults={"cooldown_group": f"graph:{MAILBOX}", **gates}
        )

    def queue_one_of_each(self):
        for kind in (BULK_KIND, TRANSACTIONAL_KIND, PLAIN_KIND):
            enqueue_job(kind=kind, dedupe_key="gate", payload={})

    def test_a_gated_campaign_lane_is_skipped_while_other_work_runs(self):
        self.gate(bulk_gate_until=self.now + timedelta(seconds=60))
        self.queue_one_of_each()

        claimed = {job.kind for job in claim_jobs(batch_size=10)}

        self.assertEqual(claimed, {TRANSACTIONAL_KIND, PLAIN_KIND})
        self.assertIn(BULK_KIND, blocked_job_kinds())
        self.assertIn("mail.email_recipient", blocked_job_kinds())
        self.assertNotIn("mail.sms_recipient", blocked_job_kinds())  # another family

    def test_transactional_jobs_are_claimed_once_their_slot_is_within_the_worker_wait(self):
        self.gate(all_gate_until=self.now + timedelta(seconds=10))
        self.assertEqual(blocked_job_kinds(), {BULK_KIND, "mail.email_recipient"})

        self.gate(all_gate_until=self.now + timedelta(seconds=120))
        self.assertTrue({BULK_KIND, TRANSACTIONAL_KIND, "event.ticket_email"} <= blocked_job_kinds())

    def test_past_gates_and_unconfigured_families_block_nothing(self):
        self.gate(all_gate_until=self.now - timedelta(seconds=1), bulk_gate_until=self.now - timedelta(seconds=1))
        self.assertEqual(blocked_job_kinds(), frozenset())

        with patch.dict(families._RESOLVERS, {rates.Family.EMAIL: f"{THIS}.no_active_channel"}):
            families.clear_gate_cache()
            self.gate(bulk_gate_until=self.now + timedelta(hours=1))
            self.assertEqual(blocked_job_kinds(), frozenset())

    def test_a_broken_resolver_blocks_nothing(self):
        with patch.dict(families._RESOLVERS, {rates.Family.EMAIL: "apps.does.not.exist"}):
            self.assertEqual(blocked_job_kinds(), frozenset())


@patch.dict(families._RESOLVERS, {rates.Family.EMAIL: f"{THIS}.active_graph_mailbox"})
@override_settings(DELIVERY_RATES=rates_with(jobs={"gate_cache_seconds": 1e-6}))
class WorkerChurnTests(RegisteredKindsTestCase):
    """Two workers on one paced campaign lane (Graph, 19.2 campaign messages a minute: one per 3.125 s)."""

    def setUp(self):
        super().setUp()
        self.clock = FakeClock(timezone.now()).install(self)
        # Sleeping never moves the clock here: the other worker claims while this one waits for its slot.
        patcher = patch("apps.core.services.delivery_rates.runtime.context.sleep")
        patcher.start()
        self.addCleanup(patcher.stop)
        families.clear_gate_cache()
        self.addCleanup(families.clear_gate_cache)
        BackgroundJob.objects.bulk_create(
            BackgroundJob(kind=BULK_KIND, dedupe_key=str(index), priority=100, available_at=self.clock.now())
            for index in range(200)
        )

    def worker_round(self):
        """One claim-and-run by a worker; its outcome, or None when it found nothing to claim (and would sleep)."""
        families.clear_gate_cache()
        jobs = claim_jobs(batch_size=1)
        return run_claimed_job(jobs[0]) if jobs else None

    def test_two_workers_defer_at_most_once_each_per_interval(self):
        outcomes = []
        for _interval in range(20):
            for _step in range(4):
                for _worker in ("a", "b"):
                    outcomes.append(self.worker_round())
            self.clock.advance(3.125)

        sent = outcomes.count(JobOutcome.SUCCEEDED)
        deferred = outcomes.count(JobOutcome.DEFERRED)
        self.assertGreaterEqual(sent, 19)
        self.assertLessEqual(deferred, 2 * 20)
        # Most rounds find the lane gated and claim nothing, so the worker loop sleeps instead of spinning.
        self.assertGreater(outcomes.count(None), len(outcomes) / 2)
        self.assertEqual(BackgroundJob.objects.filter(status=BackgroundJob.Status.FAILED).count(), 0)
