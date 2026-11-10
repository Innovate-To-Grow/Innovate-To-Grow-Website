"""The bounce processor's durable state per mailbox: checkpoint, lease and health (``EmailMonitorState``).

A scan takes the mailbox's lease first (a conditional update, never a lock held across Microsoft requests, which the
delivery-rate limiter would refuse), so two workers or a manual "Scan now" never scan one mailbox at once; an
expired lease (a worker stopped mid-scan) is simply taken over. Every write is a single statement.
"""

import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.core.models import EmailMonitorState

from ..telemetry import text


def state_for(mailbox: str) -> EmailMonitorState:
    try:
        with transaction.atomic():
            return EmailMonitorState.objects.get_or_create(mailbox=mailbox)[0]
    except IntegrityError:  # created by another process meanwhile
        return EmailMonitorState.objects.get(mailbox=mailbox)


def acquire_lease(mailbox: str, now: datetime) -> uuid.UUID | None:
    token = uuid.uuid4()
    lease_until = now + timedelta(seconds=settings.EMAIL_MONITORING["bounce_lease_seconds"])
    free = Q(lease_until__isnull=True) | Q(lease_until__lt=now)
    taken = EmailMonitorState.objects.filter(free, mailbox=mailbox, paused=False).update(
        lease_token=token, lease_until=lease_until, last_run_started_at=now, updated_at=now
    )
    return token if taken else None


def _held(mailbox: str, token: uuid.UUID):
    return EmailMonitorState.objects.filter(mailbox=mailbox, lease_token=token)


def finish(mailbox: str, token: uuid.UUID, *, checkpoint, stats: dict, error: str = "", retry_after=None) -> None:
    """Save the run's progress and outcome and give the lease back. ``error`` marks a failed run (shown on the
    dashboard); ``retry_after`` (seconds) is when Microsoft asked to be contacted again."""
    now = timezone.now()
    values = {
        "lease_token": None,
        "lease_until": None,
        "last_run_finished_at": now,
        "last_run_stats": stats,
        "next_run_after": now + timedelta(seconds=retry_after) if retry_after else None,
        "updated_at": now,
    }
    if checkpoint is not None:
        values["checkpoint_at"] = checkpoint
    if error:
        values.update(
            last_error=text.scrub(error), last_error_at=now, consecutive_failures=F("consecutive_failures") + 1
        )
    elif retry_after is None:
        # A scan held back by Microsoft's pacing (``retry_after``) neither succeeded nor failed.
        values.update(last_success_at=now, consecutive_failures=0)
    _held(mailbox, token).update(**values)


def record_problem(mailbox: str, problem: str) -> None:
    """Bounce processing cannot run for ``mailbox`` (out of scope, not allowed): shown like a failed run."""
    now = timezone.now()
    state_for(mailbox)
    EmailMonitorState.objects.filter(mailbox=mailbox).update(
        last_error=text.scrub(problem), last_error_at=now, last_run_finished_at=now, updated_at=now
    )


def set_paused(mailbox: str, paused: bool) -> None:
    state_for(mailbox)
    EmailMonitorState.objects.filter(mailbox=mailbox).update(paused=paused, updated_at=timezone.now())
