"""Rate signals: what one provider answer means for a channel's rate.

Each adapter (Graph, SES, SMTP, IMAP, Gmail API, SMS) turns a provider answer into one ``RateSignal`` using its
patterns in ``DELIVERY_RATES["signals"]``; the limiter applies it with ``runtime.feedback.record``:

========== ============================================================== =================
Kind       Effect                                                         Usage counted
========== ============================================================== =================
OK         sent; resets the throttle count; closes a breaker it probed     kept
THROTTLE   cooldown (Retry-After, else backoff) for the cooldown group;    released
           Smart rate slows down once per episode
PAUSE      the same, for the pause the settings give (too many logins …)   released
QUOTA      a daily or project quota is used up: breaker, timed re-check    released
BLOCKED    auth, permission or account stop: breaker until fixed           released
UNCERTAIN  outcome unknown: no recovery credit                             kept
NONE       about this one message only (a bad address, an opt-out)         released
========== ============================================================== =================

A THROTTLE or PAUSE marked ``uncertain`` (the request may have been processed) keeps its usage.
Free provider text is only matched against the configured patterns, never stored.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from enum import StrEnum

from django.utils import timezone

from .defaults import section

# Retry-After counts whole seconds (RFC 9110 delta-seconds), so one second is the shortest wait it can ask for.
MIN_RETRY_AFTER_SECONDS = 1.0
_DELTA_SECONDS = re.compile(r"[0-9]{1,12}")


class SignalKind(StrEnum):
    OK = "ok"
    THROTTLE = "throttle"
    PAUSE = "pause"
    QUOTA = "quota"
    BLOCKED = "blocked"
    UNCERTAIN = "uncertain"
    NONE = "none"


class Scope(StrEnum):
    """What a breaker stops: all mail of the identity, or only its campaigns (the bulk lane)."""

    ALL = "all"
    BULK = "bulk"


class Reason(StrEnum):
    """Reasons the limiter itself acts on. Adapters may use other short codes for their cooldowns and breakers."""

    AUTH = "auth"
    PERMISSION = "permission"
    ACCOUNT_PAUSED = "account_paused"
    SPEND_LIMIT = "spend_limit"
    PERSISTENT_THROTTLE = "persistent_throttle"


# Breakers that saving the matching configuration half-opens (``runtime.breaker.half_open_for_config``).
CONFIG_REASONS = frozenset({Reason.AUTH, Reason.PERMISSION})


@dataclass(frozen=True)
class RateSignal:
    kind: SignalKind
    # Short code shown on Mail → Delivery Rates (at most 64 characters, never provider text).
    reason: str = ""
    # Seconds the provider asked for (already clamped by ``parse_retry_after``).
    retry_after: float | None = None
    # Fixed pause from the settings, used when the provider names no Retry-After.
    pause_seconds: float | None = None
    # First re-check of a QUOTA or BLOCKED breaker (None: the controller's breaker probe interval).
    breaker_seconds: float | None = None
    scope: Scope = Scope.ALL
    # The request may have been processed: its usage stays counted and Smart rate gets no recovery credit.
    uncertain: bool = False


def ok() -> RateSignal:
    return RateSignal(SignalKind.OK)


def none(reason: str = "") -> RateSignal:
    return RateSignal(SignalKind.NONE, reason)


def throttle(reason: str = "throttled", *, retry_after: float | None = None, uncertain: bool = False) -> RateSignal:
    return RateSignal(SignalKind.THROTTLE, reason, retry_after=retry_after, uncertain=uncertain)


def pause(
    reason: str, *, seconds: float | None = None, retry_after: float | None = None, uncertain: bool = False
) -> RateSignal:
    return RateSignal(SignalKind.PAUSE, reason, retry_after=retry_after, pause_seconds=seconds, uncertain=uncertain)


def quota(reason: str, *, seconds: float | None = None, scope: Scope = Scope.ALL) -> RateSignal:
    return RateSignal(SignalKind.QUOTA, reason, breaker_seconds=seconds, scope=scope)


def blocked(reason: str, *, seconds: float | None = None, scope: Scope = Scope.ALL) -> RateSignal:
    return RateSignal(SignalKind.BLOCKED, reason, breaker_seconds=seconds, scope=scope)


def uncertain(reason: str = "") -> RateSignal:
    return RateSignal(SignalKind.UNCERTAIN, reason, uncertain=True)


def releases_usage(signal: RateSignal) -> bool:
    """True when the provider certainly did not take the request, so it does not count against a daily limit."""
    return signal.kind not in (SignalKind.OK, SignalKind.UNCERTAIN) and not signal.uncertain


def not_now(signal: RateSignal | None) -> bool:
    """The provider did not take the request but may later: a throttle, a pause, a used-up quota, or a stop that no
    configuration change fixes (an account pause, the SMS spend limit). Such a failure is retried, never final; the
    limiter holds the next requests back meanwhile."""
    if signal is None:
        return False
    if signal.kind in (SignalKind.THROTTLE, SignalKind.PAUSE, SignalKind.QUOTA):
        return True
    return signal.kind == SignalKind.BLOCKED and signal.reason not in CONFIG_REASONS


def parse_retry_after(value, *, now: datetime | None = None, maximum: float | None = None) -> float | None:
    """A Retry-After value (delta-seconds or an HTTP-date) in seconds, or None when absent or unreadable.

    The result is clamped to [1 s, ``controller.retry_after_max_seconds``]: a date in the past still means "wait",
    and a huge value cannot stop a channel for longer than the settings allow.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        seconds = float(value)
        if seconds != seconds or seconds < 0:  # NaN or negative
            return None
    else:
        seconds = _parse_text(str(value or "").strip(), now)
        if seconds is None:
            return None
    ceiling = float(section("controller")["retry_after_max_seconds"] if maximum is None else maximum)
    return min(max(seconds, MIN_RETRY_AFTER_SECONDS), ceiling)


def _parse_text(raw: str, now: datetime | None) -> float | None:
    if not raw:
        return None
    if _DELTA_SECONDS.fullmatch(raw):
        return float(int(raw))
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)  # HTTP-dates are always GMT
    return (when - (now or timezone.now())).total_seconds()


def code_in(code, codes) -> bool:
    """``code`` equals one of ``codes``, ignoring case."""
    folded = str(code or "").casefold()
    return bool(folded) and any(folded == str(item).casefold() for item in codes)


def text_has(text, patterns) -> bool:
    """``text`` contains one of ``patterns``, ignoring case."""
    folded = str(text or "").casefold()
    return bool(folded) and any(str(item).casefold() in folded for item in patterns)
