"""Reading and adding to the token counters directly (no reservation), and the audit-log IP helpers."""

from django.core.cache import cache
from django.utils import timezone

from apps.core.utils.client_ip import client_ip as _client_ip
from apps.core.utils.client_ip import hash_ip as _hash_ip
from apps.system_intelligence.models import PublicAssistantTokenBudget

from .database_store import _record_database_usage
from .limits import (
    _DEFAULT_WINDOW_SECONDS,
    GLOBAL_BUDGET_KEYS,
    GLOBAL_FEATURE_LABELS,
    GlobalBudgetUsage,
    _budget_window_key,
    _new_window_id,
    budget_key,
    global_budget_key,
)
from .reservations import _database_budget_enabled


def client_ip(request) -> str | None:
    """Return the originating client IP. For audit logs only -- never a limit key."""
    return _client_ip(request)


def hash_ip(ip: str) -> str:
    """Salted SHA-256 hash of an IP, recorded in audit logs. It must not key any limit."""
    return _hash_ip(ip)


def _database_tokens_used(actor_key: str) -> int:
    value = (
        PublicAssistantTokenBudget.objects.filter(
            ip_hash=actor_key,
            window_expires_at__gt=timezone.now(),
        )
        .values_list("tokens_used", flat=True)
        .first()
    )
    return int(value or 0)


def tokens_used(actor_key: str) -> int:
    if _database_budget_enabled():
        return _database_tokens_used(actor_key)
    return int(cache.get(budget_key(actor_key), 0) or 0)


def global_tokens_used(feature: str) -> int:
    """Tokens charged to ``feature``'s global budget in its current window."""
    return tokens_used(global_budget_key(feature))


def global_budget_usage() -> list[GlobalBudgetUsage]:
    """Current-window usage of every feature's global budget, for display.

    A plain read: it takes no row lock, so it can never wait for or block a
    reservation. The figures include tokens reserved by calls still in flight.
    """
    if _database_budget_enabled():
        open_windows = {
            row.pk: row
            for row in PublicAssistantTokenBudget.objects.filter(
                pk__in=list(GLOBAL_BUDGET_KEYS.values()),
                window_expires_at__gt=timezone.now(),
            )
        }
        usage = []
        for feature, label in GLOBAL_FEATURE_LABELS.items():
            row = open_windows.get(GLOBAL_BUDGET_KEYS[feature])
            usage.append(
                GlobalBudgetUsage(
                    feature=feature,
                    label=label,
                    tokens_used=int(row.tokens_used) if row is not None else 0,
                    window_expires_at=row.window_expires_at if row is not None else None,
                )
            )
        return usage
    return [
        GlobalBudgetUsage(feature=feature, label=label, tokens_used=tokens_used(GLOBAL_BUDGET_KEYS[feature]))
        for feature, label in GLOBAL_FEATURE_LABELS.items()
    ]


def check_budget(actor_key: str, limit: int) -> bool:
    """True if the actor may spend more tokens. limit <= 0 means unlimited.

    A plain read: it reserves nothing, so callers that go on to spend must use
    ``reserve_budget`` instead.
    """
    if limit <= 0:
        return True
    return tokens_used(actor_key) < limit


def record_usage(actor_key: str, tokens: int, window_seconds: int) -> None:
    """Add ``tokens`` to one counter, creating it if absent."""
    if tokens <= 0:
        return
    # A timeout of 0 (or negative) makes Django's cache discard the write
    # immediately, silently disabling the budget; clamp to a sane window.
    if window_seconds <= 0:
        window_seconds = _DEFAULT_WINDOW_SECONDS
    if _database_budget_enabled():
        _record_database_usage(actor_key, tokens, window_seconds)
        return
    key = budget_key(actor_key)
    # add() is a no-op if the key already exists, so the window is set on the
    # first write of the period and the counter rolls over when it expires.
    created = cache.add(key, 0, timeout=window_seconds)
    if created:
        cache.set(_budget_window_key(actor_key), _new_window_id(), timeout=window_seconds)
    try:
        cache.incr(key, tokens)
    except ValueError:
        # The key expired between add() and incr(); re-seed and retry once.
        created = cache.add(key, 0, timeout=window_seconds)
        if created:
            cache.set(_budget_window_key(actor_key), _new_window_id(), timeout=window_seconds)
        try:
            cache.incr(key, tokens)
        except ValueError:
            cache.set(key, tokens, timeout=window_seconds)
            cache.set(_budget_window_key(actor_key), _new_window_id(), timeout=window_seconds)
