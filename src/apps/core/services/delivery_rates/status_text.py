"""The status lines of Mail → Delivery Rates, the dashboard and the send estimates, built from ``snapshot``:

1. ``Now: 21.6 messages/min · Smart · recovering after Microsoft Graph pushed back at 14:02 UTC (full speed about
   14:42 UTC)``, or ``Paused until …`` / ``Stopped: …`` while a cooldown or breaker holds the identity;
2. ``Provider limit: 30 messages/min (documented)``;
3. one line per budget: ``Last 24 h: 1,240 / 10,000 recipients (campaigns stop at 9,000)``.

Warnings follow: a failed limit read, an Advanced limit above what the provider reports, or a carried-over limit the
provider's report has replaced.
"""

from datetime import UTC, datetime, timedelta

from apps.core.models import DeliveryRateState

from .rules.controller import full_speed_at
from .rules.policy import BoundSource, EffectiveRate
from .runtime.budget import DAY, Limit, Usage

CLOSED = DeliveryRateState.BreakerState.CLOSED
BULK_ONLY = DeliveryRateState.BreakerScope.BULK

REASONS = {
    "throttled": "asked to slow down",
    "auth": "refused the credentials",
    "permission": "refused permission for this sender",
    "account_paused": "reports sending is paused for this account",
    "spend_limit": "reports the monthly SMS spend limit is reached",
    "account_blocked": "reports the account cannot send",
    "bandwidth": "suspended the account for exceeding its bandwidth limits",
    "connections": "refused another simultaneous connection",
    "persistent_throttle": "kept throttling",
    "cooldown": "asked to wait",
    "pushback": "pushed back",
    "concurrent_requests": "refused too many requests at once",
    "sign_in_attempts": "refused more sign-in attempts for now",
    "token_endpoint": "sign-in service was busy or unreachable",
    "credential_store": "key could not be read from the credential store",
    "daily_limit": "reports the daily sending limit is reached",
    "daily_quota": "reports the 24-hour sending quota is used up",
    "daily_sending_limit": "reports the account's daily sending limit is reached",
    "project_quota": "reports the Google Cloud project's daily quota is used up",
    "submission_quota": "reports the mailbox's submission quota is used up",
    "mailbox_full": "reports the sender mailbox is full",
    "configuration_set_paused": "reports sending is paused for the configuration set",
}
_COUNTS = {"external": "external recipients", "internal": "internal recipients", "messages": "messages"}


def number(value) -> str:
    """12.6, 10, 0.45, 10,000: at most three decimals, no trailing zeros."""
    text = f"{float(value):,.3f}".rstrip("0").rstrip(".")
    return text or "0"


def clock(when: datetime, *, seconds: bool = True) -> str:
    return when.astimezone(UTC).strftime("%H:%M:%S UTC" if seconds else "%H:%M UTC")


def age(delta: timedelta) -> str:
    seconds = max(0, int(delta.total_seconds()))
    if seconds < 120:
        return f"{seconds} s"
    if seconds < 7_200:
        return f"{seconds // 60} min"
    return f"{seconds // 3_600} h"


def reason(provider: str, code: str) -> str:
    return f"{provider} {REASONS.get(code, f'stopped ({code})' if code else 'asked to wait')}"


def _source(rate: EffectiveRate, provider: str, state, now: datetime) -> str:
    source = rate.bound.source
    if source == BoundSource.REPORTED:
        return f"reported by {provider} {age(now - state.discovered_at)} ago" if state.discovered_at else "reported"
    if source == BoundSource.OPERATOR:
        return "set under Advanced"
    if source == BoundSource.CARRIED_OVER:
        return f"the old campaign send rate, until {provider} reports the account's limit"
    if source == BoundSource.DOCUMENTED:
        return "documented"
    if source == BoundSource.TENANT:
        return "the mailbox limit on the Microsoft Graph configuration"
    return "unknown: Smart rate starts from the app default; enter the real limit under Advanced"


def _smart_detail(rate: EffectiveRate, spec, state, provider: str, unit: str, now: datetime) -> str:
    if rate.factor is not None and rate.factor < 1 and state.last_cut_at is not None:
        detail = f"recovering after {provider} pushed back at {clock(state.last_cut_at, seconds=False)}"
        full = full_speed_at(state, spec, now)
        return f"{detail} (full speed about {clock(full, seconds=False)})" if full else detail
    if not rate.bound.known:
        return f"provider limit unknown, so it starts from the {number(rate.bound.value)} {unit} app default"
    share = round(100 * rate.rate / rate.bound.value)
    return f"{share}% of the {number(rate.bound.value)} {unit} limit ({_source(rate, provider, state, now)})"


def now_line(*, rate: EffectiveRate, smart_rate: float, spec, state, provider: str, unit: str, now: datetime) -> str:
    if state.breaker_state != CLOSED and state.breaker_scope != BULK_ONLY:
        retry = f" (next check {clock(state.breaker_retry_at)})" if state.breaker_retry_at else ""
        return f"Stopped: {reason(provider, state.breaker_reason)}{retry}"
    if state.cooldown_until is not None and state.cooldown_until > now:
        return f"Paused until {clock(state.cooldown_until)}: {reason(provider, state.cooldown_reason)}"
    head = f"Now: {number(rate.rate)} {unit}"
    if rate.smart:
        line = f"{head} · Smart · {_smart_detail(rate, spec, state, provider, unit, now)}"
    elif rate.manual_capped:
        source = _source(rate, provider, state, now)
        line = f"{head} · Manual · capped by the {number(rate.bound.value)} {unit} provider limit ({source})"
    else:
        line = f"{head} · Manual (Smart rate would use {number(smart_rate)})"
    if state.breaker_state != CLOSED:
        line += f" · campaigns stopped: {reason(provider, state.breaker_reason)}"
    return line


def limit_lines(*, rate: EffectiveRate, state, provider: str, unit: str, now: datetime) -> list[str]:
    lines = [f"Provider limit: {number(rate.bound.value)} {unit} ({_source(rate, provider, state, now)})"]
    if rate.parts is not None:
        parts = rate.parts
        source = {BoundSource.REPORTED: f"reported by {provider}", BoundSource.OPERATOR: "set under Advanced"}.get(
            parts.source, "unknown until AWS reports the number's rate"
        )
        lines.append(f"Message parts: {number(parts.value)} parts/sec ({source})")
    return lines


def budget_line(limit: Limit, usage: Usage, budget_unit: str) -> str:
    window = "Last 24 h" if limit.window == DAY else "Last hour"
    counts = _COUNTS.get(limit.counts, budget_unit)
    used = usage.of(limit.counts, limit.window)
    if limit.usable < limit.limit:
        stops = f"all mail stops at {limit.usable:,}, campaigns at {limit.bulk_usable:,}"
    else:
        stops = f"campaigns stop at {limit.bulk_usable:,}"
    return f"{window}: {used:,} / {limit.limit:,} {counts} ({stops})"


def warnings(*, policy, state, rate: EffectiveRate, provider: str, unit: str, now: datetime) -> list[str]:
    found = []
    if state.discovery_error:
        if state.discovered_at is not None:
            found.append(
                f"{provider} limits last read {age(now - state.discovered_at)} ago ({state.discovery_error}); "
                f"using the last known {number(rate.bound.value)} {unit}"
            )
        else:
            found.append(f"{provider} limits not read yet ({state.discovery_error})")
    reported, operator = state.discovered_rate, policy.provider_limit
    if reported and operator is not None and policy.provider_limit_carried_over:
        found.append(
            f"The provider limit carried over from the old campaign send rate ({number(operator)} {unit}) no longer "
            f"applies: {provider} reports {number(reported)} {unit}. Clear it, or enter your own limit."
        )
    elif reported and operator is not None and float(operator) > reported:
        found.append(
            f"The provider limit set under Advanced ({number(operator)} {unit}) is above the {number(reported)} "
            f"{unit} {provider} reports; {number(reported)} applies."
        )
    return found
