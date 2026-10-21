"""Token budgeting for the public assistant and the past-project AI search.

Two budgets are charged for every model call, and a request is admitted only
when it fits both:

* a per-ACTOR budget -- one visitor, one member, or the shared ``legacy`` bucket
  (see ``actors.py``; its row is charged like any other but carries no limit).
  Never the client IP: the whole campus shares one public address, so an IP key
  would be a single bucket for everybody.
* a GLOBAL budget for the FEATURE being used -- one row for the public
  assistant and one for AI search, each limited by
  ``SystemIntelligenceConfig.public_assistant_global_token_limit``. Visitor
  identities are free to obtain, so this is the real spend ceiling. The two
  rows are separate so that draining one feature (the anonymous chat can be
  scripted) can never pause the other (the members' AI search).

Backends: Redis is used when configured. Production environments without Redis
use a transactional database counter -- this is the authoritative path, the
only one that is atomic across web workers and ECS tasks -- while
tests/development may explicitly opt in to the local cache fallback. Budget
rows are keyed by an opaque 64-hex value; no IP and no raw id is stored.
"""

from dataclasses import replace

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.core.utils.client_ip import client_ip as _client_ip
from apps.core.utils.client_ip import hash_ip as _hash_ip
from apps.system_intelligence.models import PublicAssistantTokenBudget

from .cache_store import (
    _RECONCILE_SCRIPT,
    _RELEASE_SCRIPT,
    _RESERVE_SCRIPT,
    _release_cache_reservation_quietly,
    _reserve_cache_budget,
    _settle_cache_reservations,
    _shared_redis_client,
)
from .database_store import (
    _database_tokens_used,
    _record_database_usage,
    _reserve_database_budget,
    _settle_database_reservation,
    purge_expired_public_assistant_budgets,
)
from .limits import (
    _DEFAULT_WINDOW_SECONDS,
    FEATURE_AI_SEARCH,
    FEATURE_ASSISTANT,
    GLOBAL_BUDGET_KEYS,
    GLOBAL_FEATURE_LABELS,
    GLOBAL_WINDOW_SECONDS,
    BudgetBackendUnavailable,
    BudgetReservation,
    GlobalBudgetUsage,
    _budget_window_key,
    _new_window_id,
    _warn_global_budget_exhausted,
    budget_key,
    global_budget_key,
)
from .usage import MAX_REPORTED_TOKENS, _reconciled_tokens, reported_total_tokens, sanitized_usage

__all__ = [
    "FEATURE_AI_SEARCH",
    "FEATURE_ASSISTANT",
    "GLOBAL_BUDGET_KEYS",
    "GLOBAL_FEATURE_LABELS",
    "GLOBAL_WINDOW_SECONDS",
    "MAX_REPORTED_TOKENS",
    "BudgetBackendUnavailable",
    "BudgetReservation",
    "GlobalBudgetUsage",
    "budget_key",
    "check_budget",
    "client_ip",
    "global_budget_key",
    "global_budget_usage",
    "global_tokens_used",
    "hash_ip",
    "purge_expired_public_assistant_budgets",
    "reconcile_budget",
    "record_usage",
    "release_budget",
    "reported_total_tokens",
    "reserve_budget",
    "sanitized_usage",
    "tokens_used",
]


def client_ip(request) -> str | None:
    """Return the originating client IP. For audit logs only -- never a limit key."""
    return _client_ip(request)


def hash_ip(ip: str) -> str:
    """Salted SHA-256 hash of an IP, recorded in audit logs. It must not key any limit."""
    return _hash_ip(ip)


def _database_budget_enabled() -> bool:
    """Use the shared database only when Redis was intentionally left unset."""
    redis_url = str(getattr(settings, "REDIS_URL", "") or "").strip()
    local_fallback = bool(getattr(settings, "PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET", False))
    return not redis_url and not local_fallback


def _reserve_cache_pair(actor_key, global_key, *, amount, limit, window_seconds, global_limit, feature):
    """Redis / local cache: reserve the feature's global counter, then the actor's."""
    # Two single-counter reservations. Each one is atomic, and the global one
    # is given back if the actor's does not fit, so neither budget can be
    # overspent (a concurrent request may at worst be refused while the first
    # reservation is being returned). Production has no Redis and always takes
    # the single-transaction database path in ``reserve_budget``.
    global_reservation = None
    if global_limit is not None:
        global_reservation = _reserve_cache_budget(
            global_key,
            amount=amount,
            limit=global_limit,
            window_seconds=GLOBAL_WINDOW_SECONDS,
        )
        if global_reservation is None:
            _warn_global_budget_exhausted(feature, global_limit)
            return None
    try:
        reservation = _reserve_cache_budget(
            actor_key,
            amount=amount,
            limit=limit,
            window_seconds=window_seconds,
        )
    except BudgetBackendUnavailable:
        if global_reservation is not None:
            _release_cache_reservation_quietly(global_reservation)
        raise
    if reservation is None:
        if global_reservation is not None:
            _release_cache_reservation_quietly(global_reservation)
        return None
    return replace(reservation, global_reservation=global_reservation)


def reserve_budget(
    actor_key: str,
    *,
    estimated_input_tokens: int,
    maximum_output_tokens: int,
    limit: int,
    window_seconds: int,
    global_limit: int | None = None,
    feature: str | None = None,
) -> BudgetReservation | None:
    """Atomically reserve estimated input plus the maximum possible output.

    ``limit`` / ``window_seconds`` bound the actor (a visitor or a member);
    ``limit <= 0`` means no per-actor limit, which is what the shared legacy
    bucket gets (see ``actors.actor_token_limit``).

    ``global_limit`` is the spend ceiling of ``feature``
    (``SystemIntelligenceConfig.public_assistant_global_token_limit``; each of
    ``FEATURE_ASSISTANT`` and ``FEATURE_AI_SEARCH`` has its own counter with
    that limit, so one feature can never use up the other's). When given, the
    request is admitted only if it fits BOTH the actor's budget and the
    feature's global budget, and both are charged; ``0`` refuses every request
    (the model calls are switched off). ``None`` skips global accounting --
    only for callers that are not spending money on a public request.

    ``feature`` is required with ``global_limit``; an unknown one raises
    ``ValueError`` rather than charging another feature's budget.

    Returns ``None`` when the request does not fit.
    """
    global_key = global_budget_key(feature) if global_limit is not None else None
    amount = max(0, estimated_input_tokens) + max(0, maximum_output_tokens)
    window_seconds = window_seconds if window_seconds > 0 else _DEFAULT_WINDOW_SECONDS
    if global_limit is not None and global_limit <= 0:
        return None
    if _database_budget_enabled():
        try:
            return _reserve_database_budget(
                actor_key,
                amount=amount,
                limit=limit,
                window_seconds=window_seconds,
                global_limit=global_limit,
                feature=feature,
            )
        except Exception as exc:
            raise BudgetBackendUnavailable("Shared database assistant budget is unavailable.") from exc

    return _reserve_cache_pair(
        actor_key,
        global_key,
        amount=amount,
        limit=limit,
        window_seconds=window_seconds,
        global_limit=global_limit,
        feature=feature,
    )


def reconcile_budget(reservation: BudgetReservation, actual_tokens) -> None:
    """Replace the reservation with the provider's actual usage (both levels)."""
    if reservation.database:
        try:
            _settle_database_reservation(
                reservation,
                actual_tokens=_reconciled_tokens(reservation, actual_tokens),
            )
        except Exception as exc:
            raise BudgetBackendUnavailable("Could not reconcile database assistant usage.") from exc
        return
    _settle_cache_reservations(reservation, actual_tokens=_reconciled_tokens(reservation, actual_tokens))


def release_budget(reservation: BudgetReservation) -> None:
    """Give the whole reservation back (both levels), e.g. after a provider error."""
    if reservation.database:
        try:
            _settle_database_reservation(reservation, actual_tokens=None)
        except Exception as exc:
            raise BudgetBackendUnavailable("Could not release database assistant usage.") from exc
        return
    _settle_cache_reservations(reservation, actual_tokens=None)


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
