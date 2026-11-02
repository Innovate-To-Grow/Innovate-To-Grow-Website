"""Job-kind registry.

Each app that owns a job kind registers its handlers from ``AppConfig.ready()``
with dotted paths, which are imported only when a job of that kind runs — the
worker never imports a domain app it does not need, and ``core`` imports none.

A kind that delivers mail or SMS also names its delivery ``family`` and ``lane``: the worker then leaves its jobs
unclaimed while that lane is paced, cooling down or stopped, and claims them by ``priority``.
"""

from dataclasses import dataclass

from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

from apps.core.models.records.background_job import DEFAULT_JOB_PRIORITY
from apps.core.services.delivery_rates.rules.channels import Family, Lane

# Claim order of delivery jobs (lower first): login codes, tickets and notices before other work, campaigns after
# it. An ordering, not a rate: each job stores its priority when it is queued.
LANE_PRIORITIES = {Lane.TRANSACTIONAL: 10, Lane.BULK: 100}


@dataclass(frozen=True)
class JobKind:
    handler: str
    state_handler: str | None = None
    stale_resolver: str | None = None
    family: str | None = None
    lane: str | None = None
    priority: int = DEFAULT_JOB_PRIORITY


_KINDS: dict[str, JobKind] = {}


def _delivery(kind: str, family, lane, priority) -> dict:
    if (family is None) != (lane is None):
        raise ImproperlyConfigured(f"Background job kind {kind!r} must name both a delivery family and a lane.")
    if family is None:
        return {"priority": DEFAULT_JOB_PRIORITY if priority is None else priority}
    try:
        family, lane = Family(family), Lane(lane)
    except ValueError:
        raise ImproperlyConfigured(f"Background job kind {kind!r} names an unknown delivery family or lane.") from None
    return {"family": family, "lane": lane, "priority": LANE_PRIORITIES[lane] if priority is None else priority}


def register_job_kind(
    kind: str,
    *,
    handler: str,
    state_handler: str | None = None,
    stale_resolver: str | None = None,
    family: str | None = None,
    lane: str | None = None,
    priority: int | None = None,
) -> None:
    """Register the dotted-path callables that process ``kind``.

    ``handler(job)`` runs the job. ``state_handler(job)`` mirrors each outbox
    state change into a domain record. ``stale_resolver(job)`` may prove a stale
    provider job completed (returning the resolved state) before it is quarantined.
    ``family`` / ``lane`` name the delivery lane a provider-calling kind sends on; ``priority`` defaults to the
    lane's (``LANE_PRIORITIES``), or ``DEFAULT_JOB_PRIORITY``.
    Registering the same kind again is allowed only with identical values.
    """
    entry = JobKind(handler, state_handler, stale_resolver, **_delivery(kind, family, lane, priority))
    existing = _KINDS.get(kind)
    if existing is not None and existing != entry:
        raise ImproperlyConfigured(f"Background job kind {kind!r} is already registered with other handlers.")
    _KINDS[kind] = entry


def registered_job_kinds() -> dict[str, JobKind]:
    return dict(_KINDS)


def job_priority(kind: str) -> int:
    entry = _KINDS.get(kind)
    return DEFAULT_JOB_PRIORITY if entry is None else entry.priority


def get_handler(kind: str):
    entry = _KINDS.get(kind)
    if entry is None:
        raise LookupError(f"No background job handler is registered for {kind!r}.")
    return import_string(entry.handler)


def notify_job_state(job) -> None:
    """Mirror a generic outbox state into an optional domain-specific record."""

    entry = _KINDS.get(job.kind)
    if entry is None or entry.state_handler is None:
        return
    import_string(entry.state_handler)(job)


def resolve_stale_job_state(job) -> str | None:
    """Let a handler prove a stale provider job completed before quarantining it."""

    entry = _KINDS.get(job.kind)
    if entry is None or entry.stale_resolver is None:
        return None
    return import_string(entry.stale_resolver)(job)
