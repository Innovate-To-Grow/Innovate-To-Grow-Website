"""A read-only picture of every delivery channel for the admin page, the dashboard and the send estimates.

Rows are read without locks, so a status can be a moment old. A channel that has not sent yet shows its policy
against a fresh state.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from apps.core.models import DeliveryRatePolicy, DeliveryRateState

from . import status_text
from .rules.channels import channel_info
from .rules.defaults import rate_spec
from .rules.policy import EffectiveRate, effective_rate, smart_rate
from .runtime import budget, context


@dataclass(frozen=True)
class IdentityStatus:
    identity: str
    rate: EffectiveRate
    lines: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    cooldown_until: datetime | None = None
    breaker_open: bool = False
    breaker_reason: str = ""
    limits: tuple[budget.Limit, ...] = ()

    @property
    def headline(self) -> str:
        return self.lines[0]


@dataclass(frozen=True)
class ChannelStatus:
    channel: str
    label: str
    unit: str
    smart_enabled: bool
    manual_rate: Decimal
    identities: tuple[IdentityStatus, ...] = field(default_factory=tuple)

    @property
    def headline(self) -> str:
        return self.identities[0].headline


def _usage(state, now: datetime) -> budget.Usage:
    if state.pk is None or state._state.adding:
        empty = dict.fromkeys(budget.COLUMNS, 0)
        return budget.Usage(day=empty, hour=dict(empty))
    return budget.usage(state, now)


def identity_status(policy, state, now: datetime) -> IdentityStatus:
    spec = rate_spec(policy.channel)
    provider, unit = channel_info(policy.channel).provider, policy.unit.label
    rate = effective_rate(policy, state, spec, now)
    shared = {"rate": rate, "state": state, "provider": provider, "unit": unit, "now": now}
    lines = [
        status_text.now_line(smart_rate=smart_rate(policy, state, spec, now), spec=spec, **shared),
        *status_text.limit_lines(**shared),
    ]
    limits = tuple(budget.limits(policy, state))
    if limits:
        used = _usage(state, now)
        lines.extend(status_text.budget_line(limit, used, policy.unit.budget) for limit in limits)
    return IdentityStatus(
        identity=state.identity,
        rate=rate,
        lines=tuple(lines),
        warnings=tuple(status_text.warnings(policy=policy, **shared)),
        cooldown_until=state.cooldown_until if state.cooldown_until and state.cooldown_until > now else None,
        breaker_open=state.breaker_state != DeliveryRateState.BreakerState.CLOSED,
        breaker_reason=state.breaker_reason,
        limits=limits,
    )


def channel_status(channel: str, *, now: datetime | None = None) -> ChannelStatus:
    now = now or context.clock()
    policy = DeliveryRatePolicy.for_channel(channel)
    states = list(DeliveryRateState.objects.filter(channel=channel).order_by("identity"))
    if not states:
        states = [DeliveryRateState(channel=channel, identity="", cooldown_group="")]
    return ChannelStatus(
        channel=channel,
        label=policy.get_channel_display(),
        unit=policy.unit.label,
        smart_enabled=policy.smart_enabled,
        manual_rate=policy.manual_rate,
        identities=tuple(identity_status(policy, state, now) for state in states),
    )


def snapshot(channels=None, *, now: datetime | None = None) -> list[ChannelStatus]:
    """Every channel's status (or those in ``channels``), in the channel order of ``DeliveryRatePolicy``."""
    now = now or context.clock()
    names = list(channels) if channels is not None else list(DeliveryRatePolicy.Channel.values)
    return [channel_status(name, now=now) for name in names]
