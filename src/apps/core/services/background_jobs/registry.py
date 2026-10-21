"""Job-kind registry.

Each app that owns a job kind registers its handlers from ``AppConfig.ready()``
with dotted paths, which are imported only when a job of that kind runs — the
worker never imports a domain app it does not need, and ``core`` imports none.
"""

from dataclasses import dataclass

from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string


@dataclass(frozen=True)
class JobKind:
    handler: str
    state_handler: str | None = None
    stale_resolver: str | None = None


_KINDS: dict[str, JobKind] = {}


def register_job_kind(
    kind: str,
    *,
    handler: str,
    state_handler: str | None = None,
    stale_resolver: str | None = None,
) -> None:
    """Register the dotted-path callables that process ``kind``.

    ``handler(job)`` runs the job. ``state_handler(job)`` mirrors each outbox
    state change into a domain record. ``stale_resolver(job)`` may prove a stale
    provider job completed (returning the resolved state) before it is quarantined.
    Registering the same kind again is allowed only with identical paths.
    """
    entry = JobKind(handler, state_handler, stale_resolver)
    existing = _KINDS.get(kind)
    if existing is not None and existing != entry:
        raise ImproperlyConfigured(f"Background job kind {kind!r} is already registered with other handlers.")
    _KINDS[kind] = entry


def registered_job_kinds() -> dict[str, JobKind]:
    return dict(_KINDS)


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
