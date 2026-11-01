"""Locking a channel identity's ``DeliveryRateState`` row, and the guard that keeps admissions out of callers'
transactions."""

import logging

from django.conf import settings
from django.core import mail
from django.db import IntegrityError, connections, transaction

from apps.core.models import DeliveryRateState

from . import context

logger = logging.getLogger(__name__)


class AdmissionInTransaction(RuntimeError):
    """The limiter was called inside a caller's ``transaction.atomic``: its row lock would be held until the
    caller commits, across the provider call, so every other sender would wait behind it."""


def _in_caller_atomic(using: str) -> bool:
    # TestCase wraps every test in atomic blocks of its own, marked ``_from_testcase``; only a caller's counts.
    return any(not getattr(block, "_from_testcase", False) for block in connections[using].atomic_blocks)


def _strict() -> bool:
    # Django's test runner installs ``mail.outbox`` (setup_test_environment): raise there and in DEBUG.
    return settings.DEBUG or hasattr(mail, "outbox")


def ensure_outside_atomic(operation: str, using: str = "default") -> None:
    """Raise in tests and DEBUG, warn in production, when the limiter runs inside a caller's transaction."""
    if not _in_caller_atomic(using):
        return
    message = (
        f"Delivery-rate {operation} ran inside transaction.atomic; send after commit (transaction.on_commit) so "
        "no lock is held across the provider call."
    )
    if _strict():
        raise AdmissionInTransaction(message)
    logger.warning(message)


def _inherited_cooldown(cooldown_group: str, now) -> dict:
    """A new identity starts inside any cooldown its group is in (a Graph read 429 also stops sends)."""
    active = (
        DeliveryRateState.objects.filter(cooldown_group=cooldown_group, cooldown_until__gt=now)
        .order_by("-cooldown_until")
        .values("cooldown_until", "cooldown_reason")
        .first()
    )
    return active or {}


def locked_state(channel: str, identity: str, cooldown_group: str) -> DeliveryRateState:
    """Lock the identity's row inside the caller's (the limiter's own) transaction, creating it first if needed."""
    rows = DeliveryRateState.objects.select_for_update()
    try:
        return rows.get(channel=channel, identity=identity)
    except DeliveryRateState.DoesNotExist:
        pass
    try:
        with transaction.atomic():
            DeliveryRateState.objects.create(
                channel=channel,
                identity=identity,
                cooldown_group=cooldown_group,
                **_inherited_cooldown(cooldown_group, context.clock()),
            )
    except IntegrityError:
        pass  # another process created it first
    return rows.get(channel=channel, identity=identity)


def relock(state_id) -> DeliveryRateState | None:
    """Lock an existing row again (for feedback); None when it was purged meanwhile."""
    return DeliveryRateState.objects.select_for_update().filter(pk=state_id).first()
