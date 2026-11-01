"""Durable PostgreSQL outbox: queue, claim (by priority, skipping gated delivery lanes), retry and worker metrics.

Domain apps register their job kinds with ``register_job_kind`` in ``AppConfig.ready()``;
provider-calling handlers share the helpers in ``delivery``.
"""

from .metrics import publish_worker_metrics, worker_metrics
from .queue import (
    enqueue_job,
    jobs_enabled,
    retry_job,
)
from .recovery import recover_stale_jobs
from .registry import register_job_kind, registered_job_kinds
from .worker import (
    DeferredJobError,
    JobClaimLost,
    JobOutcome,
    PermanentJobError,
    TransientJobError,
    UncertainJobError,
    claim_jobs,
    process_claimed_job,
    run_claimed_job,
)

__all__ = [
    "DeferredJobError",
    "JobOutcome",
    "TransientJobError",
    "PermanentJobError",
    "UncertainJobError",
    "JobClaimLost",
    "claim_jobs",
    "enqueue_job",
    "jobs_enabled",
    "process_claimed_job",
    "publish_worker_metrics",
    "recover_stale_jobs",
    "register_job_kind",
    "registered_job_kinds",
    "retry_job",
    "run_claimed_job",
    "worker_metrics",
]
