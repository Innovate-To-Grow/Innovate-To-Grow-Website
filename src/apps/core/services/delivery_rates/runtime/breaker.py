"""Breakers: stop an identity (all mail, or only its campaigns) when the provider says it cannot send at all, until
a timed probe, a provider report or a staff action shows it is clear.

Every breaker has a timed probe: at ``breaker_retry_at`` exactly one request goes through as the probe. Its
success closes the breaker; another stop reopens it with the probe interval doubled (up to the controller's
maximum); an unclear outcome reopens it with the same interval. Saving the matching configuration lets the next
request probe at once for auth and permission stops.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from django.utils import timezone

from apps.core.models import DeliveryRateState

from ..rules.channels import Lane
from ..rules.defaults import RateSpec
from ..rules.signals import CONFIG_REASONS, RateSignal, Reason, Scope, SignalKind

CLOSED = DeliveryRateState.BreakerState.CLOSED
OPEN = DeliveryRateState.BreakerState.OPEN
HALF_OPEN = DeliveryRateState.BreakerState.HALF_OPEN
_STOPS = (SignalKind.QUOTA, SignalKind.BLOCKED)
_RESET_FIELDS = {
    "breaker_state": CLOSED,
    "breaker_scope": "",
    "breaker_reason": "",
    "breaker_retry_at": None,
    "breaker_interval_seconds": None,
    "breaker_probe_id": None,
    "breaker_probe_started_at": None,
}


@dataclass(frozen=True)
class Gate:
    blocked: bool
    until: datetime | None = None
    probe: bool = False


def applies(state, lane: str) -> bool:
    """The breaker stops ``lane`` (a campaigns-only breaker lets transactional mail through)."""
    if state.breaker_state == CLOSED:
        return False
    return state.breaker_scope != Scope.BULK or lane == Lane.BULK


def gate(state, lane: str, now: datetime) -> Gate:
    """Closed, open until ``until``, or due: then this request may go through as the probe."""
    if not applies(state, lane):
        return Gate(blocked=False)
    if state.breaker_retry_at is not None and now < state.breaker_retry_at:
        return Gate(blocked=True, until=state.breaker_retry_at)
    return Gate(blocked=False, probe=True)


def take_probe(state, now: datetime) -> uuid.UUID:
    """Let this request through as the probe; nobody else probes before the next interval."""
    probe_id = uuid.uuid4()
    state.breaker_state = HALF_OPEN
    state.breaker_probe_id = probe_id
    state.breaker_probe_started_at = now
    state.breaker_retry_at = now + timedelta(seconds=state.breaker_interval_seconds or 0)
    return probe_id


def _next_month(now: datetime) -> datetime:
    current = now.astimezone(UTC)
    year, month = (current.year + 1, 1) if current.month == 12 else (current.year, current.month + 1)
    return datetime(year, month, 1, tzinfo=UTC)


def open_breaker(state, *, reason: str, scope: str, seconds: float, spec: RateSpec, now: datetime, failed_probe: bool):
    """Stop the identity. A failed probe of the same stop doubles the interval; a request that was already in
    flight when the breaker opened changes nothing but may widen it to all mail."""
    if state.breaker_state != CLOSED and not failed_probe:
        if scope == Scope.ALL:
            state.breaker_scope = Scope.ALL
            state.all_gate_until = state.breaker_retry_at
        return
    interval = seconds
    if failed_probe and state.breaker_reason == reason and state.breaker_interval_seconds:
        interval = max(seconds, min(spec.breaker_probe_max, state.breaker_interval_seconds * 2))
    retry_at = now + timedelta(seconds=interval)
    if reason == Reason.SPEND_LIMIT:
        # AWS resets the monthly spend at the start of each month, so the probe is due then at the latest.
        retry_at = min(retry_at, max(now, _next_month(now)))
    state.breaker_state = OPEN
    state.breaker_scope = scope
    state.breaker_reason = str(reason)[:64]
    state.breaker_interval_seconds = max(1, round(interval))
    state.breaker_retry_at = retry_at
    state.breaker_probe_id = state.breaker_probe_started_at = None
    if scope == Scope.ALL:
        state.all_gate_until = retry_at
    else:
        state.bulk_gate_until = retry_at


def close_breaker(state) -> None:
    for name, value in _RESET_FIELDS.items():
        setattr(state, name, value)
    state.all_gate_until = state.bulk_gate_until = None


def settle(state, admission, signal: RateSignal, spec: RateSpec, now: datetime) -> None:
    """Apply a provider answer to the breaker: a stop opens it; the probe's own answer closes or reopens it."""
    probe = admission.probe_id is not None and admission.probe_id == state.breaker_probe_id
    if signal.kind in _STOPS:
        seconds = signal.breaker_seconds or spec.breaker_probe
        open_breaker(
            state,
            reason=signal.reason or signal.kind,
            scope=signal.scope,
            seconds=seconds,
            spec=spec,
            now=now,
            failed_probe=probe,
        )
        return
    if not probe:
        return
    still_throttled = signal.kind in (SignalKind.THROTTLE, SignalKind.PAUSE)
    if still_throttled and state.breaker_reason == Reason.PERSISTENT_THROTTLE:
        open_breaker(
            state,
            reason=Reason.PERSISTENT_THROTTLE,
            scope=Scope.ALL,
            seconds=spec.breaker_probe,
            spec=spec,
            now=now,
            failed_probe=True,
        )
    elif signal.kind == SignalKind.UNCERTAIN:
        state.breaker_state = OPEN
        state.breaker_probe_id = state.breaker_probe_started_at = None
        state.breaker_retry_at = now + timedelta(seconds=state.breaker_interval_seconds or spec.breaker_probe)
    else:
        close_breaker(state)


def config_stopped(channels):
    """The channels' identities stopped by an auth or permission breaker, which a configuration save may fix."""
    rows = DeliveryRateState.objects.filter(channel__in=list(channels), breaker_reason__in=list(CONFIG_REASONS))
    return rows.exclude(breaker_state=CLOSED)


def half_open_for_config(channels, now: datetime) -> int:
    """After a configuration save: let the next request probe the channels' auth and permission breakers now."""
    return config_stopped(channels).update(
        breaker_retry_at=now,
        breaker_probe_id=None,
        breaker_probe_started_at=None,
        all_gate_until=None,
        bulk_gate_until=None,
        updated_at=now,
    )


def resume(channel: str, identity: str | None = None, now: datetime | None = None) -> int:
    """Staff's "Resume sending": close the breakers and end the cooldowns of the channel (or one identity)."""
    now = now or timezone.now()
    rows = DeliveryRateState.objects.filter(channel=channel)
    if identity is not None:
        rows = rows.filter(identity=identity)
    return rows.update(
        **_RESET_FIELDS,
        cooldown_until=None,
        cooldown_reason="",
        consecutive_throttles=0,
        all_gate_until=None,
        bulk_gate_until=None,
        updated_at=now,
    )
