"""The Message Trace sync's durable state per sender (``EmailDeliveryTraceState``): lease, health and backoff.

A sync takes the sender's lease first (a conditional update, never a lock held across Microsoft requests), and only
once ``next_run_after`` has passed, so two workers or a manual "Sync now" never trace at once and a backoff holds for
every caller. An expired lease (a worker stopped mid-sync) is simply taken over.
"""

import uuid
from datetime import datetime, timedelta

from django.db import IntegrityError, transaction
from django.db.models import Case, F, Q, Value, When
from django.utils import timezone

from apps.core.models import EmailDeliveryTraceState

from ...telemetry import text

Permission = EmailDeliveryTraceState.Permission
# Microsoft refused the permission: ask again after six hours (granting it and its service principal takes hours).
NOT_PERMITTED_BACKOFF_SECONDS = 6 * 3600
# Throttled: Retry-After, at least five minutes, doubling while it repeats, at most an hour.
THROTTLE_FLOOR_SECONDS = 300
THROTTLE_CAP_SECONDS = 3600
LEASE_FLOOR_SECONDS = 900


def state_for(sender: str) -> EmailDeliveryTraceState:
    try:
        with transaction.atomic():
            return EmailDeliveryTraceState.objects.get_or_create(sender=sender)[0]
    except IntegrityError:  # created by another process meanwhile
        return EmailDeliveryTraceState.objects.get(sender=sender)


def acquire_lease(sender: str, now: datetime, seconds: float) -> uuid.UUID | None:
    """Take the sender's lease for *seconds*, unless another sync holds it or the backoff has not passed."""
    token = uuid.uuid4()
    free = Q(lease_until__isnull=True) | Q(lease_until__lt=now)
    due = Q(next_run_after__isnull=True) | Q(next_run_after__lte=now)
    taken = EmailDeliveryTraceState.objects.filter(free, due, sender=sender).update(
        lease_token=token,
        lease_until=now + timedelta(seconds=max(LEASE_FLOOR_SECONDS, seconds)),
        last_run_started_at=now,
        updated_at=now,
    )
    return token if taken else None


def throttle_delay(previous_throttles: int, retry_after: float | None) -> int:
    """Seconds to wait after a throttle: Retry-After (five minutes at least), doubled for each throttle in a row."""
    base = max(float(retry_after or 0), THROTTLE_FLOOR_SECONDS)
    return int(min(THROTTLE_CAP_SECONDS, base * 2 ** min(max(previous_throttles, 0), 8)))


def finish(
    sender: str,
    token: uuid.UUID,
    *,
    stats: dict,
    error: str = "",
    delay: int | None = None,
    permission: str | None = None,
    succeeded: bool = False,
) -> None:
    """Save the run's outcome and give the lease back. ``error`` marks a failed run; ``delay`` (seconds) is the
    backoff before the next sync; ``permission`` is what the run learned of the trace permission (``UNKNOWN`` only
    ends a "not permitted": a permission Microsoft confirmed earlier stays)."""
    now = timezone.now()
    values = {
        "lease_token": None,
        "lease_until": None,
        "last_run_finished_at": now,
        "last_run_stats": stats,
        "next_run_after": now + timedelta(seconds=delay) if delay else None,
        "updated_at": now,
    }
    if permission == Permission.UNKNOWN:
        values["permission"] = Case(
            When(permission=Permission.NOT_PERMITTED, then=Value(Permission.UNKNOWN)), default=F("permission")
        )
    elif permission:
        values["permission"] = permission
    if error:
        values.update(
            last_error=text.scrub(error), last_error_at=now, consecutive_failures=F("consecutive_failures") + 1
        )
    elif succeeded:
        values.update(last_success_at=now, consecutive_failures=0)
    EmailDeliveryTraceState.objects.filter(sender=sender, lease_token=token).update(**values)


def record_problem(sender: str, problem: str) -> None:
    """The sync cannot run for ``sender`` (out of scope): shown like a failed run, no lease taken."""
    now = timezone.now()
    state_for(sender)
    EmailDeliveryTraceState.objects.filter(sender=sender).update(
        last_error=text.scrub(problem), last_error_at=now, last_run_finished_at=now, updated_at=now
    )


def clear_not_permitted(sender: str) -> int:
    """Microsoft answered a trace request for *sender* (the permission check): end a "not permitted" backoff, so
    the next sync (or "Sync now") runs at once instead of waiting out the six hours."""
    return EmailDeliveryTraceState.objects.filter(sender=sender, permission=Permission.NOT_PERMITTED).update(
        permission=Permission.UNKNOWN, next_run_after=None, updated_at=timezone.now()
    )
