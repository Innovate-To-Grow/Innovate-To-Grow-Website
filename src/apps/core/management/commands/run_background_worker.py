import json
import logging
import signal
import time

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.authn.services.login_guard import purge_expired_failure_windows
from apps.authn.services.security.rsa_manager import purge_retired_auth_keypairs
from apps.authn.services.send_verification import cleanup_expired_records, clear_expired_sessions
from apps.core.services.background_jobs import (
    claim_jobs,
    process_claimed_job,
    publish_worker_metrics,
    recover_stale_jobs,
    worker_metrics,
)
from apps.system_intelligence.services.public_assistant import purge_expired_public_assistant_budgets

logger = logging.getLogger(__name__)

DEFAULT_MAINTENANCE_SECONDS = 3600
MIN_MAINTENANCE_SECONDS = 300


def _purge_retired_keys(should_stop=None) -> None:
    if purge_retired_auth_keypairs():
        # Keep key material and values derived from the key store out of logs. The static event is enough for
        # operators; detailed counts belong in controlled metrics.
        logger.info("Purged retired RSA keypair rows")


def _purge_public_assistant_budgets(should_stop=None) -> None:
    if purge_expired_public_assistant_budgets():
        # Do not log counts or IP-derived identifiers. Operators only need confirmation that maintenance is active.
        logger.info("Purged expired public assistant budget rows")


def _cleanup_send_verification(should_stop=None) -> None:
    result = cleanup_expired_records(should_stop=should_stop)
    if any(result.values()):
        logger.info(
            "Send verification cleanup: expired %(expired_challenges)d challenges; deleted %(deleted_challenges)d "
            "challenges and %(deleted_requests)d send requests",
            result,
        )


def _clear_expired_sessions(should_stop=None) -> None:
    cleared = clear_expired_sessions(should_stop=should_stop)
    if cleared:
        logger.info("Cleared %d expired sessions", cleared)


def _purge_login_failure_windows(should_stop=None) -> None:
    # Only windows that have already ended are deleted, so this never lifts a password-login lockout early.
    if purged := purge_expired_failure_windows(should_stop=should_stop):
        logger.info("Purged %d expired login failure windows", purged)


# Periodic maintenance, run in this order every ``--maintenance-seconds`` (hourly by default). Each entry is
# ``(name, callable)``; ``run_maintenance`` isolates every call, so one failure never stops the worker or the rest.
# Every callable takes the stop check: the three batched tasks hand it to their batch loops, so a stop request ends
# them after the batch in flight; the two single-statement purges ignore it.
MAINTENANCE_TASKS = (
    ("Retired RSA key purge", _purge_retired_keys),
    ("Public assistant budget purge", _purge_public_assistant_budgets),
    ("Send verification cleanup", _cleanup_send_verification),
    ("Expired session cleanup", _clear_expired_sessions),
    ("Login failure window purge", _purge_login_failure_windows),
)


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
        from apps.cms.services.amplify.amplify_redirects import schedule_amplify_redirect_sync

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
        parser.add_argument("--stale-minutes", type=int, default=10)
        parser.add_argument(
            "--maintenance-seconds",
            "--key-purge-seconds",  # the original name, kept for existing invocations
            dest="key_purge_seconds",
            type=int,
            default=DEFAULT_MAINTENANCE_SECONDS,
            help=f"Seconds between maintenance runs (minimum {MIN_MAINTENANCE_SECONDS}).",
        )

    def handle(self, *args, **options):
        stopping = False

        def request_stop(_signum, _frame):
            nonlocal stopping
            stopping = True

        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)
        poll_seconds = min(30.0, max(0.25, options["poll_seconds"]))
        batch_size = max(1, options["batch_size"])
        maintenance_seconds = max(
            MIN_MAINTENANCE_SECONDS, options.get("key_purge_seconds", DEFAULT_MAINTENANCE_SECONDS)
        )
        next_maintenance_at = 0.0
        schedule_startup_reconciliation()

        while not stopping:
            from datetime import timedelta

            now_monotonic = time.monotonic()
            if now_monotonic >= next_maintenance_at:
                try:
                    run_maintenance(should_stop=lambda: stopping)
                finally:
                    next_maintenance_at = now_monotonic + maintenance_seconds

            processed_jobs = 0
            try:
                recover_stale_jobs(stale_after=timedelta(minutes=max(1, options["stale_minutes"])))
            except Exception:  # noqa: BLE001 - one maintenance failure must not terminate the worker.
                logger.exception("Background worker maintenance/claim cycle failed")
            else:
                # Claim immediately before execution instead of reserving a whole
                # batch. If a shutdown signal arrives while one job is running,
                # later jobs remain pending and do not consume an attempt merely
                # because this worker is stopping.
                for _index in range(batch_size):
                    if stopping:
                        break
                    try:
                        jobs = claim_jobs(batch_size=1)
                    except Exception:  # noqa: BLE001 - retry the claim on the next cycle.
                        logger.exception("Background worker maintenance/claim cycle failed")
                        break
                    if not jobs:
                        break
                    job = jobs[0]
                    processed_jobs += 1
                    try:
                        process_claimed_job(job)
                    except Exception:  # noqa: BLE001 - final per-job containment boundary.
                        logger.exception("Unhandled background job boundary failure for %s", job.pk)

            try:
                metrics = worker_metrics()
                publish_worker_metrics(metrics)
                self.stdout.write(json.dumps(metrics, sort_keys=True))
            except Exception:  # noqa: BLE001 - observability must not terminate delivery.
                logger.exception("Background worker metrics cycle failed")

            if options["once"]:
                return
            # No idle wait once a stop was requested: the loop condition ends the worker right away.
            if not processed_jobs and not stopping:
                time.sleep(poll_seconds)
