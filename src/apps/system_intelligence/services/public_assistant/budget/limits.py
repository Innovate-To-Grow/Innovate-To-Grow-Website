"""The budgets' shape: features, window lengths, global row keys, and the reservation record."""

import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from django.core.cache import cache

logger = logging.getLogger("apps.system_intelligence.services.public_assistant.budget")

# Fallback window if a non-positive value is configured: in Django, a cache
# timeout of 0 means "expire immediately / do not store", which would silently
# disable the budget. Clamp to a 1-day rolling window instead.
_DEFAULT_WINDOW_SECONDS = 86400

# The features that spend money, each with its OWN global budget row. Every
# model call is charged to exactly one of them.
FEATURE_ASSISTANT = "assistant"
FEATURE_AI_SEARCH = "ai-search"
GLOBAL_FEATURE_LABELS = {
    FEATURE_ASSISTANT: "Public assistant",
    FEATURE_AI_SEARCH: "AI search",
}
# Primary keys of the global rows. Fixed public constants (not secrets): actor
# keys are keyed hashes, so none of them can collide with these.
GLOBAL_BUDGET_KEYS = {
    feature: hashlib.sha256(f"public-assistant:global-budget:{feature}".encode()).hexdigest()
    for feature in GLOBAL_FEATURE_LABELS
}
# A global budget is "tokens per 24 hours". Each feature's window opens with
# its own first charge after its previous window ended.
GLOBAL_WINDOW_SECONDS = 86400


class BudgetBackendUnavailable(RuntimeError):
    """Raised when the shared budget backend cannot be reached."""


class _GlobalBudgetExhausted(Exception):
    """Internal: unwinds the reserve transaction when the global row is full."""


def global_budget_key(feature: str) -> str:
    """Primary key of the global budget row of ``feature``.

    An unknown feature is a programming error, never a reason to charge some
    other feature's budget, so it raises instead of falling back.
    """
    try:
        return GLOBAL_BUDGET_KEYS[feature]
    except (KeyError, TypeError):
        raise ValueError(f"Unknown assistant budget feature: {feature!r}") from None


@dataclass(frozen=True)
class GlobalBudgetUsage:
    """What one feature's global budget has been charged in its current window."""

    feature: str
    label: str
    tokens_used: int
    # End of the open window. ``None`` when no window is open (nothing has been
    # charged since the last one ended) or the backend does not expose it.
    window_expires_at: datetime | None = None


@dataclass(frozen=True)
class BudgetReservation:
    budget_cache_key: str
    window_cache_key: str
    reservation_cache_key: str
    reserved_tokens: int
    window_seconds: int
    shared_redis: bool
    database: bool = False
    # Primary key of the charged ``PublicAssistantTokenBudget`` row.
    actor_key: str = ""
    window_id: int = 0
    database_reservation_id: uuid.UUID | None = None
    # The matching charge against the global budget (two-level reservations).
    global_reservation: "BudgetReservation | None" = None


def budget_key(actor_key: str) -> str:
    return f"assistant:tokens:{actor_key}"


def _budget_window_key(actor_key: str) -> str:
    return f"assistant:tokens-window:{actor_key}"


def _new_window_id() -> int:
    # Keep the marker within Redis's signed 64-bit integer range. django-redis
    # stores Python integers without pickling, so Lua and cache-based callers
    # observe the same decimal value.
    return (uuid.uuid4().int & ((1 << 63) - 1)) or 1


def _reservation_key() -> str:
    return f"assistant:reservation:{uuid.uuid4().hex}"


def _warn_global_budget_exhausted(feature: str, global_limit: int) -> None:
    """Operator alarm for a spend ceiling: at most one line a minute per feature and container."""
    try:
        first_this_minute = cache.add(f"assistant:global-budget-exhausted-warned:{feature}", 1, timeout=60)
    except Exception:  # noqa: BLE001 - a cache fault must not turn a refusal into an error
        first_this_minute = True
    if first_this_minute:
        logger.warning(
            "Assistant global token budget exhausted for %s (limit %s per %ss): its model calls are refused "
            "until its window ends or the Global Token Limit is raised in Django admin (System Intelligence > "
            "Assistant Tools). The other feature has its own budget and is not affected.",
            GLOBAL_FEATURE_LABELS.get(feature, feature),
            global_limit,
            GLOBAL_WINDOW_SECONDS,
        )
