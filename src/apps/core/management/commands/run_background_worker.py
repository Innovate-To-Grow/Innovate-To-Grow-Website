import json
import logging
import signal
import time

from django.core.management.base import BaseCommand

from apps.authn.services.rsa_manager import purge_retired_auth_keypairs
from apps.core.services.background_jobs import (
    claim_jobs,
    process_claimed_job,
    publish_worker_metrics,
    recover_stale_jobs,
    worker_metrics,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the PostgreSQL-backed durable background-job worker."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Claim one batch and exit.")
        parser.add_argument("--batch-size", type=int, default=10)
        parser.add_argument("--poll-seconds", type=float, default=5.0)
        parser.add_argument("--stale-minutes", type=int, default=10)
        parser.add_argument("--key-purge-seconds", type=int, default=3600)

    def handle(self, *args, **options):
        stopping = False

        def request_stop(_signum, _frame):
            nonlocal stopping
            stopping = True

        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)
        poll_seconds = min(30.0, max(0.25, options["poll_seconds"]))
        batch_size = max(1, options["batch_size"])
        key_purge_seconds = max(300, options.get("key_purge_seconds", 3600))
        next_key_purge_at = 0.0

        while not stopping:
            from datetime import timedelta

            now_monotonic = time.monotonic()
            if now_monotonic >= next_key_purge_at:
                try:
                    deleted = purge_retired_auth_keypairs()
                    if deleted:
                        logger.info("Purged %s retired RSA keypair row(s)", deleted)
                except Exception:  # noqa: BLE001 - maintenance must not stop delivery.
                    logger.exception("Retired RSA key purge failed")
                finally:
                    next_key_purge_at = now_monotonic + key_purge_seconds

            try:
                recover_stale_jobs(stale_after=timedelta(minutes=max(1, options["stale_minutes"])))
                jobs = claim_jobs(batch_size=batch_size)
            except Exception:  # noqa: BLE001 - one maintenance failure must not terminate the worker.
                logger.exception("Background worker maintenance/claim cycle failed")
                jobs = []
            for job in jobs:
                try:
                    process_claimed_job(job)
                except Exception:  # noqa: BLE001 - final per-job containment boundary.
                    logger.exception("Unhandled background job boundary failure for %s", job.pk)
                if stopping:
                    break

            try:
                metrics = worker_metrics()
                publish_worker_metrics(metrics)
                self.stdout.write(json.dumps(metrics, sort_keys=True))
            except Exception:  # noqa: BLE001 - observability must not terminate delivery.
                logger.exception("Background worker metrics cycle failed")

            if options["once"]:
                return
            if not jobs:
                time.sleep(poll_seconds)
