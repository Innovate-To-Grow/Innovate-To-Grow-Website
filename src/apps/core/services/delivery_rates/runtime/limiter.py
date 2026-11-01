"""Admission: one short transaction per attempt that locks the identity's state, checks its breaker, budgets and
pace, takes a slot, and commits. The caller then sleeps until the slot outside any transaction, calls the provider,
and settles the admission with ``feedback.record`` (or ``feedback.release`` when it never calls).

A caller that may wait (``max_wait``, default: the wait mode's cap) waits for its slot; one that would wait longer
gets ``RateDeferred`` and is certainly not sent. Campaigns never reserve more than one bulk interval ahead, so they
cannot push transactional mail behind a queue of future slots. Only a dedicated campaign thread (or a caller giving
``max_wait``) keeps waiting beyond that; a worker gets ``RateDeferred`` and moves on to other jobs.
"""

from datetime import datetime, timedelta
from functools import partial

from django.db import transaction

from apps.core.models import DeliveryRatePolicy

from ..rules import controller, pacing
from ..rules.channels import Lane
from ..rules.channels import cooldown_group as group_of
from ..rules.defaults import rate_spec
from ..rules.policy import effective_rate, rate_bound
from . import budget, context, discovery
from .admission import Admission, Costs, RateDeferred
from .breaker import gate, take_probe
from .state import ensure_outside_atomic, locked_state


def admit(
    channel: str,
    identity: str,
    *,
    lane: str = Lane.TRANSACTIONAL,
    pace_cost: float = 1,
    budget_cost: int = 0,
    external_cost: int = 0,
    message_cost: int = 0,
    parts: int | None = None,
    max_wait: float | None = None,
    cooldown_group: str | None = None,
) -> Admission:
    """Take a slot for one request on ``channel`` for ``identity``, waiting for it up to ``max_wait`` seconds.

    Raises ``RateDeferred`` (try again at ``until``) or ``RateRefused`` (never fits a daily limit). The returned
    admission must be settled with ``record`` or ``release``.
    """
    lane = Lane(lane)
    costs = Costs(pace=pace_cost, budget=budget_cost, external=external_cost, messages=message_cost, parts=parts)
    default_group = group_of(channel, identity)  # also checks that the identity fits its column
    group = cooldown_group or default_group
    ensure_outside_atomic("admission")
    cap = context.wait_cap() if max_wait is None else max(0.0, float(max_wait))
    keeps_waiting = (
        lane != Lane.BULK or max_wait is not None or context.current_wait_mode() == context.WaitMode.DEDICATED
    )
    deadline = context.clock() + timedelta(seconds=cap)
    while True:
        outcome = _attempt(channel, identity, group, lane, costs, deadline)
        if isinstance(outcome, Admission):
            _sleep_until(outcome.send_at)
            return outcome
        if outcome.until > deadline or not keeps_waiting:
            raise outcome
        _sleep_until(outcome.resume_at)


def _sleep_until(when: datetime) -> None:
    seconds = (when - context.clock()).total_seconds()
    if seconds > 0:
        context.sleep(seconds)


def _attempt(channel, identity, group, lane, costs, deadline) -> Admission | RateDeferred:
    policy = DeliveryRatePolicy.for_channel(channel)
    spec = rate_spec(channel)
    with transaction.atomic():
        state = locked_state(channel, identity, group)
        now = context.clock()
        controller.sync_mode(state, policy.smart_enabled, spec, now, limit_known=rate_bound(policy, state, spec).known)
        outcome = _decide(state, policy, spec, lane, costs, now, deadline)
        refresh = discovery.claim_due(state, now)
        state.save()
        if isinstance(outcome, Admission):
            outcome.bucket_start = budget.add(state, costs, lane, now)
        if refresh:
            transaction.on_commit(partial(discovery.start_refresh, channel, identity), robust=True)
    return outcome


def _defer(state, lane, until, reason, now, resume_at=None) -> RateDeferred:
    # Hints for the worker: this lane sends nothing before ``until``.
    if lane == Lane.BULK:
        state.bulk_gate_until = until
    else:
        state.all_gate_until = until
    return RateDeferred(until, reason, now=now, resume_at=resume_at)


def _decide(state, policy, spec, lane, costs, now, deadline) -> Admission | RateDeferred:
    breaker = gate(state, lane, now)
    if breaker.blocked:
        return _defer(state, lane, breaker.until, f"breaker:{state.breaker_reason}", now)
    over_budget = budget.check(state, policy, lane, costs, now)
    if over_budget is not None:
        return _defer(state, lane, over_budget.until, over_budget.reason, now)
    rate = effective_rate(policy, state, spec, now)
    bulk = lane == Lane.BULK
    slot = pacing.next_slot(
        now=now,
        tat=state.tat,
        tat_bulk=state.tat_bulk,
        cooldown_until=state.cooldown_until,
        increment=pacing.increment_seconds(rate, costs.pace, costs.parts),
        tolerance=pacing.tolerance_seconds(rate),
        bulk_share=spec.bulk_share if bulk else None,
    )
    horizon = max(timedelta(0), deadline - now)
    if bulk:
        horizon = min(horizon, timedelta(seconds=slot.bulk_increment))
    if slot.at - now > horizon:
        cooling = state.cooldown_until is not None and state.cooldown_until > now
        resume_at = slot.at - timedelta(seconds=slot.bulk_increment) if bulk else None
        return _defer(state, lane, slot.at, "cooldown" if cooling else "pace", now, resume_at)
    admission = Admission(
        channel=state.channel,
        identity=state.identity,
        cooldown_group=state.cooldown_group,
        lane=lane,
        state_id=state.pk,
        admitted_at=now,
        send_at=slot.at,
        mode=state.mode,
        costs=costs,
        tat_before=state.tat,
        tat_after=slot.tat,
        tat_bulk_before=state.tat_bulk if bulk else None,
        tat_bulk_after=slot.tat_bulk,
        probe_id=take_probe(state, now) if breaker.probe else None,
    )
    state.tat = slot.tat
    if bulk:
        state.tat_bulk, state.bulk_gate_until = slot.tat_bulk, None
    else:
        state.all_gate_until = None
    return admission
