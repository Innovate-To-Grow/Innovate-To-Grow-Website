"""The Smart rate controller (AIMD) and the cooldown after a throttle.

Smart rate runs at ``bound × headroom × factor``. A throttle or pushback multiplies the factor by
``decrease_factor`` once per episode (a request admitted before the last cut cannot cut again), never below
``floor``; recovery is lazy: ``factor(now) = base + recovery_step × whole recovery intervals since the last
change``, capped at 1. The functions change the state object in memory only; ``runtime`` saves it.
"""

import math
import random
from datetime import datetime, timedelta

from apps.core.models import DeliveryRateState

from .defaults import RateSpec
from .signals import RateSignal

SMART = DeliveryRateState.Mode.SMART
MANUAL = DeliveryRateState.Mode.MANUAL
# Jitter only spreads retries; it needs no cryptographic randomness.
_RANDOM = random.Random()  # nosec B311


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def start_factor(spec: RateSpec, *, limit_known: bool) -> float:
    """The factor Smart rate starts at: lower while the bound is only the channel's fallback (limit unknown)."""
    return spec.start_factor if limit_known else spec.start_factor_without_limit


def current_factor(state, spec: RateSpec, now: datetime, *, limit_known: bool = True) -> float:
    """The Smart rate factor at ``now``, in [floor, 1]. A state not yet running Smart rate starts fresh."""
    if state.mode != SMART:
        return start_factor(spec, limit_known=limit_known)
    steps = 0
    changed = state.factor_changed_at
    if changed is not None and now > changed:
        steps = math.floor((now - changed).total_seconds() / spec.recovery_interval)
    return _clamp(state.factor_base + spec.recovery_step * steps, spec.floor, 1.0)


def sync_mode(state, smart: bool, spec: RateSpec, now: datetime, *, limit_known: bool) -> bool:
    """Notice a Smart rate switch lazily from ``state.mode``; return True when the mode changed.

    Switching Smart rate on starts the factor afresh. Switching it off needs nothing: the manual rate is read
    directly. Cooldowns and breakers the provider caused survive either switch.
    """
    mode = SMART if smart else MANUAL
    if state.mode == mode:
        return False
    if smart:
        state.factor_base = start_factor(spec, limit_known=limit_known)
        state.factor_changed_at = now
        state.last_cut_at = None
    state.mode = mode
    return True


def cut(state, spec: RateSpec, now: datetime, admitted_at: datetime) -> bool:
    """Slow Smart rate down after a throttle, once per episode; return True when the factor was cut."""
    if state.mode != SMART:
        return False
    if state.last_cut_at is not None and state.last_cut_at >= admitted_at:
        return False
    state.factor_base = max(spec.floor, current_factor(state, spec, now) * spec.decrease_factor)
    state.factor_changed_at = now
    state.last_cut_at = now
    return True


def freeze(state, spec: RateSpec, now: datetime) -> None:
    """Keep the factor where it is and restart the recovery clock (no recovery credit for an unclear outcome)."""
    if state.mode != SMART:
        return
    state.factor_base = current_factor(state, spec, now)
    state.factor_changed_at = now


def full_speed_at(state, spec: RateSpec, now: datetime) -> datetime | None:
    """When the recovering factor reaches 1 again, or None when it is there already."""
    factor = current_factor(state, spec, now)
    if state.mode != SMART or factor >= 1.0 or state.factor_changed_at is None:
        return None
    # Rounded first so float noise (0.6 / 0.1 = 6.000000000000001) does not add an interval.
    steps = math.ceil(round((1.0 - state.factor_base) / spec.recovery_step, 9))
    return state.factor_changed_at + timedelta(seconds=steps * spec.recovery_interval)


def backoff_seconds(consecutive: int, spec: RateSpec, rng: random.Random | None = None) -> float:
    """The pause after the ``consecutive``-th throttle in a row that named no wait: doubling up to the maximum,
    spread by ± ``backoff_jitter``."""
    doublings_to_max = math.ceil(math.log2(spec.backoff_max / spec.backoff_initial)) if spec.backoff_max > 0 else 0
    exponent = min(max(0, consecutive - 1), max(0, doublings_to_max))
    base = min(spec.backoff_max, spec.backoff_initial * 2**exponent)
    spread = base * spec.backoff_jitter
    return max(0.0, base + (rng or _RANDOM).uniform(-spread, spread))


def cooldown_seconds(signal: RateSignal, consecutive: int, spec: RateSpec, rng: random.Random | None = None) -> float:
    """How long a THROTTLE or PAUSE stops the cooldown group: the provider's Retry-After, else the pause the
    settings give for this answer, else the backoff."""
    if signal.retry_after is not None:
        return signal.retry_after
    if signal.pause_seconds is not None:
        return float(signal.pause_seconds)
    return backoff_seconds(consecutive, spec, rng)
