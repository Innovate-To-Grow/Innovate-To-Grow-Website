from datetime import timedelta
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone

from apps.core.models import BackgroundJob, DeliveryRateState
from apps.core.services import delivery_rates as rates
from apps.core.services.background_jobs import (
    JobOutcome,
    claim_jobs,
    enqueue_job,
    run_claimed_job,
)
from apps.core.services.background_jobs.gating import blocked_job_kinds
from apps.core.services.delivery_rates import families
from apps.core.tests.services.delivery_rates.helpers import FakeClock, rates_with
from apps.core.tests.services.platform.jobs.test_background_job_deferrals import (
    BULK_KIND,
    MAILBOX,
    PLAIN_KIND,
    THIS,
    TRANSACTIONAL_KIND,
    RegisteredKindsTestCase,
)


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
