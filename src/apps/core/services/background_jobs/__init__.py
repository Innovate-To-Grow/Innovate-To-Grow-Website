"""Durable PostgreSQL outbox: queue, claim, retry, rate-limit and worker metrics.

Domain apps register their job kinds with ``register_job_kind`` in ``AppConfig.ready()``;
provider-calling handlers share the helpers in ``delivery``.
"""

from .metrics import publish_worker_metrics, worker_metrics
from .queue import (
    enqueue_job,
    jobs_enabled,
    retry_job,
)
from .rate_limit import (
    configured_ses_rate,
    reserve_delivery_slot,
    wait_for_delivery_slot,
)
from .recovery import recover_stale_jobs
from .registry import register_job_kind, registered_job_kinds
from .worker import (
    JobClaimLost,
    PermanentJobError,
    TransientJobError,
    UncertainJobError,
    claim_jobs,
    process_claimed_job,
)

__all__ = [
    "TransientJobError",
    "PermanentJobError",
    "UncertainJobError",
    "JobClaimLost",
    "claim_jobs",
    "configured_ses_rate",
    "enqueue_job",
    "jobs_enabled",
    "process_claimed_job",
    "publish_worker_metrics",
    "recover_stale_jobs",
    "register_job_kind",
    "registered_job_kinds",
    "reserve_delivery_slot",
    "retry_job",
    "worker_metrics",
    "wait_for_delivery_slot",
]
