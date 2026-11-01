"""Provider feedback: ``record`` applies the answer to one admitted request, ``release`` gives back a slot that was
never used, and ``controlled`` wraps a provider call in admit → call → record. Each is one short transaction.

A throttle's cooldown also stops the rest of the identity's cooldown group; that update runs after this
transaction commits, so no process ever holds two state locks at once.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import Q

from apps.core.models import DeliveryRateState

from ..rules import controller
from ..rules.channels import channel_info
from ..rules.defaults import RateSpec, rate_spec, section
from ..rules.signals import RateSignal, Reason, Scope, SignalKind, ok, releases_usage, uncertain
from . import budget, context
from .admission import Admission
from .breaker import open_breaker, settle
from .limiter import admit
from .state import ensure_outside_atomic, relock

_THROTTLES = (SignalKind.THROTTLE, SignalKind.PAUSE)


def record(admission: Admission, signal: RateSignal | None) -> None:
    """Apply the provider's answer to an admitted request (None: the outcome is unknown)."""
    if admission.settled:
        return
    ensure_outside_atomic("feedback")
    admission.settled = True
    signal = signal or uncertain()
    spec = rate_spec(admission.channel)
    with transaction.atomic():
        state = relock(admission.state_id)
        if state is None:
            return
        now = context.clock()
        cooldown = _apply(state, admission, signal, spec, now)
        settle(state, admission, signal, spec, now)
        state.save()
        if releases_usage(signal):
            budget.release(admission)
    if cooldown is not None:
        _spread_cooldown(admission, cooldown, state.cooldown_reason, now)


def _apply(state, admission: Admission, signal: RateSignal, spec: RateSpec, now: datetime) -> datetime | None:
    """Counters, cooldown and Smart rate factor; return the new cooldown end when this answer set one."""
    state.last_signal, state.last_signal_at = signal.kind, now
    if signal.kind in (SignalKind.OK, SignalKind.NONE):
        state.consecutive_throttles = 0
        if signal.kind == SignalKind.OK:
            state.last_success_at = now
        return None
    if signal.kind not in _THROTTLES:
        if signal.kind == SignalKind.UNCERTAIN:
            controller.freeze(state, spec, now)
        return None
    state.consecutive_throttles += 1
    until = now + timedelta(seconds=controller.cooldown_seconds(signal, state.consecutive_throttles, spec))
    cooldown = None
    if state.cooldown_until is None or until > state.cooldown_until:
        state.cooldown_until, state.cooldown_reason, cooldown = until, (signal.reason or signal.kind)[:64], until
        state.all_gate_until = max(state.all_gate_until or until, until)
    # Manual rate never slows down by itself, but still honours the pause.
    if not (admission.mode == controller.SMART and controller.cut(state, spec, now, admission.admitted_at)):
        if signal.uncertain:
            controller.freeze(state, spec, now)
    if state.consecutive_throttles >= spec.persistent_throttle_count:
        open_breaker(
            state,
            reason=Reason.PERSISTENT_THROTTLE,
            scope=Scope.ALL,
            seconds=spec.breaker_probe,
            spec=spec,
            now=now,
            failed_probe=False,
        )
    if channel_info(state.channel).discovers:
        _refresh_soon(state, now)
    return cooldown


def _refresh_soon(state, now: datetime) -> None:
    """A throttle may mean the provider's limit changed: re-read it, but at most once per refresh interval."""
    gap = timedelta(seconds=section("discovery")["min_refresh_after_throttle_seconds"])
    soon = now if state.discovered_at is None else max(now, state.discovered_at + gap)
    if state.discovery_next_at is None or soon < state.discovery_next_at:
        state.discovery_next_at = soon


def _spread_cooldown(admission: Admission, until: datetime, reason: str, now: datetime) -> None:
    DeliveryRateState.objects.filter(cooldown_group=admission.cooldown_group).exclude(pk=admission.state_id).filter(
        Q(cooldown_until__isnull=True) | Q(cooldown_until__lt=until)
    ).update(cooldown_until=until, cooldown_reason=reason, updated_at=now)


def release(admission: Admission) -> None:
    """Give back an admission that never reached the provider: its slot (when no later one was taken), its daily
    budget and, for a probe, the probe."""
    if admission.settled:
        return
    ensure_outside_atomic("release")
    admission.settled = True
    with transaction.atomic():
        state = relock(admission.state_id)
        if state is None:
            return
        if state.tat == admission.tat_after:
            state.tat = admission.tat_before
        if admission.tat_bulk_after is not None and state.tat_bulk == admission.tat_bulk_after:
            state.tat_bulk = admission.tat_bulk_before
        if admission.probe_id is not None and state.breaker_probe_id == admission.probe_id:
            state.breaker_probe_id = state.breaker_probe_started_at = None
            state.breaker_retry_at = context.clock()
        state.save()
        budget.release(admission)


@contextmanager
def controlled(
    channel: str, identity: str, *, classify: Callable[[Exception], RateSignal | None] | None = None, **admit_options
) -> Iterator[Admission]:
    """``with controlled(channel, identity, lane=...) as admission:`` admits, runs the block, then records
    ``admission.signal`` (default OK), or for an exception ``classify(exc)`` (default UNCERTAIN)."""
    admission = admit(channel, identity, **admit_options)
    try:
        yield admission
    except Exception as exc:
        record(admission, (classify(exc) if classify else None) or uncertain("exception"))
        raise
    record(admission, admission.signal or ok())


def reset_smart(channel: str, identity: str | None = None) -> int:
    """Staff's "Reset Smart rate": the next request starts Smart rate afresh (cooldowns and breakers stay)."""
    rows = DeliveryRateState.objects.filter(channel=channel)
    if identity is not None:
        rows = rows.filter(identity=identity)
    return rows.update(mode="", last_cut_at=None, consecutive_throttles=0, updated_at=context.clock())
