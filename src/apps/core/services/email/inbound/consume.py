"""The consumer's side of the inbound queue: claim the oldest due row, then settle it.

A consumer claims one row at a time (``select_for_update(skip_locked=True)`` on PostgreSQL, so two workers never take
the same row), processes it outside the claim, and settles it: ``done`` with what it made of it, ``retry`` after a
failure (backoff; ``failed`` after the last attempt, shown to staff with a Retry button), ``defer`` when Microsoft
asked to wait (the attempt is given back), or ``skip`` when the message is gone from the mailbox. A row a stopped
worker left ``processing`` goes back to the queue (``recover_stale``). Nothing is dropped silently.
"""

from datetime import datetime, timedelta

from django.db import connection, transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.core.models import InboundMessage

from ..telemetry import text

Status = InboundMessage.Status
# The first retry waits this long; each later one twice as long, up to the cap.
RETRY_BASE_SECONDS = 60
RETRY_MAX_SECONDS = 6 * 3600


def _due(now: datetime):
    return InboundMessage.objects.filter(
        Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now), status=Status.PENDING
    )


def claim_next(*, now: datetime | None = None) -> InboundMessage | None:
    """Take the oldest due row (by received time, so a thread's parent is normally stored before its reply)."""
    now = now or timezone.now()
    with transaction.atomic():
        queryset = _due(now).order_by("received_at", "created_at")
        if connection.features.has_select_for_update:
            queryset = queryset.select_for_update(skip_locked=connection.features.has_select_for_update_skip_locked)
        row = queryset.first()
        if row is None:
            return None
        InboundMessage.objects.filter(pk=row.pk).update(
            status=Status.PROCESSING, attempts=F("attempts") + 1, updated_at=now
        )
    row.refresh_from_db()
    return row


def next_due_at(*, now: datetime | None = None) -> datetime | None:
    """When the next pending row falls due: ``now`` if one is due already, else its retry time; None if none waits."""
    now = now or timezone.now()
    if _due(now).exists():
        return now
    return (
        InboundMessage.objects.filter(status=Status.PENDING, next_attempt_at__gt=now)
        .order_by("next_attempt_at")
        .values_list("next_attempt_at", flat=True)
        .first()
    )


def _settle(row: InboundMessage, **values) -> None:
    values.setdefault("updated_at", timezone.now())
    InboundMessage.objects.filter(pk=row.pk, status=Status.PROCESSING).update(**values)


def done(row: InboundMessage, *, classification: str = "", subtype: str = "", result: dict | None = None) -> None:
    now = timezone.now()
    _settle(
        row,
        status=Status.DONE,
        classification=classification[:32],
        subtype=subtype[:32],
        result=result or {},
        last_error="",
        next_attempt_at=None,
        processed_at=now,
        updated_at=now,
    )


def retry(row: InboundMessage, error: str, *, max_attempts: int, now: datetime | None = None) -> bool:
    """A failed attempt: back to the queue after a backoff, or ``failed`` after the last one; True when it failed."""
    now = now or timezone.now()
    row.refresh_from_db(fields=["attempts"])
    if row.attempts >= max(1, max_attempts):
        _settle(row, status=Status.FAILED, last_error=text.scrub(error), processed_at=now, updated_at=now)
        return True
    delay = min(RETRY_MAX_SECONDS, RETRY_BASE_SECONDS * 2 ** max(0, row.attempts - 1))
    _settle(
        row,
        status=Status.PENDING,
        last_error=text.scrub(error),
        next_attempt_at=now + timedelta(seconds=delay),
        updated_at=now,
    )
    return False


def defer(row: InboundMessage, until: datetime) -> None:
    """Microsoft asked to wait: back to the queue at ``until``, and this attempt does not count."""
    _settle(row, status=Status.PENDING, attempts=F("attempts") - 1, next_attempt_at=until)


def skip(row: InboundMessage, reason: str, *, result: dict | None = None) -> None:
    now = timezone.now()
    _settle(
        row, status=Status.SKIPPED, last_error=text.scrub(reason), result=result or {}, processed_at=now, updated_at=now
    )


def requeue(queryset) -> int:
    """Staff's Retry: failed or skipped rows go back to the queue with their attempts reset; how many."""
    return queryset.filter(status__in=(Status.FAILED, Status.SKIPPED)).update(
        status=Status.PENDING,
        attempts=0,
        next_attempt_at=None,
        last_error="",
        processed_at=None,
        updated_at=timezone.now(),
    )


def recover_stale(*, stale_after: timedelta, now: datetime | None = None) -> int:
    """Rows left ``processing`` longer than ``stale_after`` (a worker stopped mid-message) go back to the queue."""
    now = now or timezone.now()
    return InboundMessage.objects.filter(status=Status.PROCESSING, updated_at__lt=now - stale_after).update(
        status=Status.PENDING, next_attempt_at=None, updated_at=now
    )
