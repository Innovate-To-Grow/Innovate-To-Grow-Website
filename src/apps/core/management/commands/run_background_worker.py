import json
import logging
import signal
import time
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.core.management.operations.worker_maintenance import MAINTENANCE_TASKS
from apps.core.services.background_jobs import (
    JobOutcome,
    claim_jobs,
    publish_worker_metrics,
    recover_stale_jobs,
    run_claimed_job,
    worker_metrics,
)
from apps.core.services.delivery_rates.rules.defaults import section

logger = logging.getLogger(__name__)

DEFAULT_MAINTENANCE_SECONDS = 3600
MIN_MAINTENANCE_SECONDS = 300


def run_maintenance(tasks=None, *, should_stop=None) -> None:
    """Run each maintenance task once, in order; log (never raise) a failure and move on to the next task.

    ``should_stop`` (the worker's shutdown flag) is checked before every task and passed to each task, which checks
    it before every batch: a stop request ends the run after the batch in flight, with every finished batch already
    committed. What is left waits for the next run.
    """
    for name, task in MAINTENANCE_TASKS if tasks is None else tasks:
        if should_stop is not None and should_stop():
            return
        try:
            task(should_stop)
        except Exception:  # noqa: BLE001 - maintenance must not stop delivery or the remaining tasks.
            logger.exception("%s failed", name)


def schedule_startup_reconciliation() -> bool:
    """Bootstrap edge rules once this deployment's durable worker is online."""

    if not getattr(settings, "BACKGROUND_JOBS_ENABLED", False):
        return False
    if not str(getattr(settings, "AMPLIFY_APP_ID", "") or "").strip():
        return False

    try:
        # Local import keeps the generic queue reusable without making the core
        # app import CMS models during Django startup.
        from apps.cms.services.amplify.jobs import schedule_amplify_redirect_sync

        job = schedule_amplify_redirect_sync(immediate=True)
    except Exception:  # noqa: BLE001 - startup scheduling must not stop delivery.
        logger.exception("Could not schedule startup Amplify reconciliation")
        return False

    if job is not None:
        logger.info("Scheduled startup Amplify reconciliation")
        return True
    return False


class Command(BaseCommand):
    help = "Run the PostgreSQL-backed durable background-job worker."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Claim one batch and exit.")
        parser.add_argument("--batch-size", type=int, default=10)
        parser.add_argument("--poll-seconds", type=float, default=5.0)
        parser.add_argument(
            "--stale-minutes",
            type=int,
            default=None,
            help='Minutes after which a claimed job is recovered (default: DELIVERY_RATES["jobs"]["stale_claim_seconds"]).',
        )
        parser.add_argument(
            "--maintenance-seconds",
            "--key-purge-seconds",  # the original name, kept for existing invocations
            dest="key_purge_seconds",
            type=int,
            default=DEFAULT_MAINTENANCE_SECONDS,
            help=f"Seconds between maintenance runs (minimum {MIN_MAINTENANCE_SECONDS}).",
        )

    def handle(self, *args, **options):
        self._stopping = False

        def request_stop(_signum, _frame):
            self._stopping = True

        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)
        poll_seconds = min(30.0, max(0.25, options["poll_seconds"]))
        batch_size = max(1, options["batch_size"])
        maintenance_seconds = max(
            MIN_MAINTENANCE_SECONDS, options.get("key_purge_seconds", DEFAULT_MAINTENANCE_SECONDS)
        )
        stale_minutes = options["stale_minutes"]
        if stale_minutes is None:
            stale_after = timedelta(seconds=section("jobs")["stale_claim_seconds"])
        else:
            stale_after = timedelta(minutes=max(1, stale_minutes))
        next_maintenance_at = 0.0
        schedule_startup_reconciliation()

        while not self._stopping:
            now_monotonic = time.monotonic()
            if now_monotonic >= next_maintenance_at:
                try:
                    run_maintenance(should_stop=lambda: self._stopping)
                finally:
                    next_maintenance_at = now_monotonic + maintenance_seconds

            processed_jobs = self._process_jobs(batch_size=batch_size, stale_after=stale_after)
            self._publish_metrics()

            if options["once"]:
                return
            # No idle wait once a stop was requested: the loop condition ends the worker right away. A round in which
            # every job was only deferred by its delivery rate also waits, so a paced lane never makes it spin.
            if not processed_jobs and not self._stopping:
                time.sleep(poll_seconds)

    def _process_jobs(self, *, batch_size: int, stale_after) -> int:
        """Recover stale jobs, then claim and run up to ``batch_size`` jobs one at a time; how many ran (a job its
        delivery rate deferred did not)."""
        try:
            recover_stale_jobs(stale_after=stale_after)
        except Exception:  # noqa: BLE001 - one maintenance failure must not terminate the worker.
            logger.exception("Background worker maintenance/claim cycle failed")
            return 0
        # Claim immediately before execution instead of reserving a whole
        # batch. If a shutdown signal arrives while one job is running,
        # later jobs remain pending and do not consume an attempt merely
        # because this worker is stopping.
        processed_jobs = 0
        for _index in range(batch_size):
            if self._stopping:
                break
            try:
                jobs = claim_jobs(batch_size=1)
            except Exception:  # noqa: BLE001 - retry the claim on the next cycle.
                logger.exception("Background worker maintenance/claim cycle failed")
                break
            if not jobs:
                break
            job = jobs[0]
            try:
                outcome = run_claimed_job(job)
            except Exception:  # noqa: BLE001 - final per-job containment boundary.
                logger.exception("Unhandled background job boundary failure for %s", job.pk)
                outcome = JobOutcome.FAILED
            if outcome != JobOutcome.DEFERRED:
                processed_jobs += 1
        return processed_jobs

    def _publish_metrics(self) -> None:
        try:
            metrics = worker_metrics()
            publish_worker_metrics(metrics)
            self.stdout.write(json.dumps(metrics, sort_keys=True))
        except Exception:  # noqa: BLE001 - observability must not terminate delivery.
            logger.exception("Background worker metrics cycle failed")
