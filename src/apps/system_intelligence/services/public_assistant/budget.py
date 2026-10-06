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

import hashlib
import logging
import threading
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.core.utils.client_ip import client_ip as _client_ip
from apps.core.utils.client_ip import hash_ip as _hash_ip
from apps.system_intelligence.models import (
    PublicAssistantTokenBudget,
    PublicAssistantTokenReservation,
)

logger = logging.getLogger(__name__)

# Fallback window if a non-positive value is configured: in Django, a cache
# timeout of 0 means "expire immediately / do not store", which would silently
# disable the budget. Clamp to a 1-day rolling window instead.
_DEFAULT_WINDOW_SECONDS = 86400
_LOCAL_RESERVATION_LOCK = threading.Lock()

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


_RESERVE_SCRIPT = """
local current_raw = redis.call('GET', KEYS[1])
local current = tonumber(current_raw or '0')
local amount = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local window_ms = tonumber(ARGV[3])
local proposed_window_id = ARGV[4]
if limit > 0 and current + amount > limit then
  return -1
end

local budget_ttl
local window_id
if current_raw then
  redis.call('INCRBY', KEYS[1], amount)
  budget_ttl = redis.call('PTTL', KEYS[1])
  if budget_ttl <= 0 then
    budget_ttl = window_ms
    redis.call('PEXPIRE', KEYS[1], budget_ttl)
  end
  window_id = redis.call('GET', KEYS[2]) or proposed_window_id
else
  budget_ttl = window_ms
  window_id = proposed_window_id
  redis.call('PSETEX', KEYS[1], budget_ttl, amount)
end

-- All state for one fixed budget window shares its remaining lifetime. A
-- reservation must never survive the counter it was charged to, otherwise a
-- late reconcile could alter the next window.
redis.call('PSETEX', KEYS[2], budget_ttl, window_id)
redis.call('PSETEX', KEYS[3], budget_ttl, tostring(amount) .. ':' .. window_id)
return current + amount
"""

_RECONCILE_SCRIPT = """
local reservation = redis.call('GET', KEYS[3])
if not reservation then
  return 0
end
local separator = string.find(reservation, ':', 1, true)
if not separator then
  redis.call('DEL', KEYS[3])
  return 0
end
local reserved = tonumber(string.sub(reservation, 1, separator - 1))
local reservation_window_id = string.sub(reservation, separator + 1)
local active_window_id = redis.call('GET', KEYS[2])
if not reserved or not active_window_id or
   active_window_id ~= reservation_window_id or
   redis.call('EXISTS', KEYS[1]) == 0 then
  redis.call('DEL', KEYS[3])
  return 0
end
local actual = tonumber(ARGV[1])
local delta = actual - reserved
if delta ~= 0 then
  redis.call('INCRBY', KEYS[1], delta)
end
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
if current < 0 then
  local ttl = redis.call('PTTL', KEYS[1])
  if ttl > 0 then
    redis.call('PSETEX', KEYS[1], ttl, 0)
  else
    redis.call('DEL', KEYS[1])
    redis.call('DEL', KEYS[2])
  end
end
redis.call('DEL', KEYS[3])
return 1
"""

_RELEASE_SCRIPT = """
local reservation = redis.call('GET', KEYS[3])
if not reservation then
  return 0
end
local separator = string.find(reservation, ':', 1, true)
if not separator then
  redis.call('DEL', KEYS[3])
  return 0
end
local reserved = tonumber(string.sub(reservation, 1, separator - 1))
local reservation_window_id = string.sub(reservation, separator + 1)
local active_window_id = redis.call('GET', KEYS[2])
if not reserved or not active_window_id or
   active_window_id ~= reservation_window_id or
   redis.call('EXISTS', KEYS[1]) == 0 then
  redis.call('DEL', KEYS[3])
  return 0
end
redis.call('INCRBY', KEYS[1], -reserved)
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
if current < 0 then
  local ttl = redis.call('PTTL', KEYS[1])
  if ttl > 0 then
    redis.call('PSETEX', KEYS[1], ttl, 0)
  else
    redis.call('DEL', KEYS[1])
    redis.call('DEL', KEYS[2])
  end
end
redis.call('DEL', KEYS[3])
return 1
"""


def client_ip(request) -> str | None:
    """Return the originating client IP. For audit logs only -- never a limit key."""
    return _client_ip(request)


def hash_ip(ip: str) -> str:
    """Salted SHA-256 hash of an IP, recorded in audit logs. It must not key any limit."""
    return _hash_ip(ip)


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


def _shared_redis_client():
    try:
        from django_redis import get_redis_connection

        return get_redis_connection("default")
    except Exception as exc:
        if getattr(settings, "PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET", False):
            return None
        raise BudgetBackendUnavailable("Shared assistant budget is unavailable.") from exc


def _database_budget_enabled() -> bool:
    """Use the shared database only when Redis was intentionally left unset."""
    redis_url = str(getattr(settings, "REDIS_URL", "") or "").strip()
    local_fallback = bool(getattr(settings, "PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET", False))
    return not redis_url and not local_fallback


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


def _locked_database_budget(budget_pk: str, *, window_seconds: int) -> PublicAssistantTokenBudget:
    initial_now = timezone.now()
    state, _created = PublicAssistantTokenBudget.objects.select_for_update().get_or_create(
        ip_hash=budget_pk,
        defaults={
            "window_id": _new_window_id(),
            "tokens_used": 0,
            "window_expires_at": initial_now + timedelta(seconds=window_seconds),
        },
    )
    # Refresh the clock only after acquiring the row lock. A request queued at
    # a window boundary must not make a decision using pre-lock time.
    now = timezone.now()
    expires_at = now + timedelta(seconds=window_seconds)
    if state.window_expires_at <= now:
        state.window_id = _new_window_id()
        state.tokens_used = 0
        state.window_expires_at = expires_at
    elif _created:
        state.window_expires_at = expires_at
    return state


def _charge_database_budget(
    state: PublicAssistantTokenBudget,
    *,
    amount: int,
    window_seconds: int,
) -> BudgetReservation:
    """Add ``amount`` to a row this transaction has locked and record the reservation."""
    state.tokens_used += amount
    state.save(update_fields=["window_id", "tokens_used", "window_expires_at"])
    database_reservation = PublicAssistantTokenReservation.objects.create(
        budget=state,
        window_id=state.window_id,
        reserved_tokens=amount,
    )
    return BudgetReservation(
        budget_cache_key=budget_key(state.pk),
        window_cache_key=_budget_window_key(state.pk),
        reservation_cache_key="",
        reserved_tokens=amount,
        window_seconds=window_seconds,
        shared_redis=False,
        database=True,
        actor_key=state.pk,
        window_id=state.window_id,
        database_reservation_id=database_reservation.pk,
    )


def _reserve_database_budget(
    actor_key: str,
    *,
    amount: int,
    limit: int,
    window_seconds: int,
    global_limit: int | None = None,
    feature: str | None = None,
) -> BudgetReservation | None:
    """Reserve ``amount`` against the actor row and, if asked, ``feature``'s global row.

    Both charges are made in ONE transaction, so a request is admitted only if
    it fits both budgets and concurrent requests can never overspend either.

    LOCK ORDER (PostgreSQL row locks): the feature's global row first, then the
    actor row. A transaction locks at most ONE global row (its own feature's)
    and at most ONE actor row, always in that order, and settlement takes the
    same two locks in the same order. So a transaction that is waiting for a
    global row holds no budget row at all, and a transaction that holds an
    actor row never waits for another budget row: whoever holds an actor row
    runs to commit, which makes a cycle in the wait graph impossible -- also
    when one member is charged by both features at once (two different global
    rows, one shared actor row). Every other path holds at most one budget row
    lock (``record_usage``), never waits for one (the purge uses ``SKIP
    LOCKED``) or takes none (the admin usage read-out).
    """
    # Match the Redis semantics: an impossible request must not create and
    # anchor an otherwise-empty fixed budget window.
    if limit > 0 and amount > limit:
        return None
    if global_limit is not None and amount > global_limit:
        _warn_global_budget_exhausted(feature, global_limit)
        return None
    try:
        with transaction.atomic():
            global_state = None
            if global_limit is not None:
                global_state = _locked_database_budget(
                    global_budget_key(feature),
                    window_seconds=GLOBAL_WINDOW_SECONDS,
                )
                if global_state.tokens_used + amount > global_limit:
                    raise _GlobalBudgetExhausted
            state = _locked_database_budget(actor_key, window_seconds=window_seconds)
            if limit > 0 and state.tokens_used + amount > limit:
                return None
            global_reservation = None
            if global_state is not None:
                global_reservation = _charge_database_budget(
                    global_state,
                    amount=amount,
                    window_seconds=GLOBAL_WINDOW_SECONDS,
                )
            reservation = _charge_database_budget(state, amount=amount, window_seconds=window_seconds)
    except _GlobalBudgetExhausted:
        _warn_global_budget_exhausted(feature, global_limit)
        return None
    return replace(reservation, global_reservation=global_reservation)


def _settle_database_reservation(
    reservation: BudgetReservation,
    *,
    actual_tokens: int | None,
) -> None:
    """Consume a database reservation exactly once.

    ``actual_tokens=None`` releases the full reservation. A successful
    reconcile stores the provider's actual usage. Each reservation row is
    deleted in the same transaction as its counter change, so repeats and
    cross-worker retries are harmless. A two-level reservation settles its
    global part and its actor part together.
    """
    # Global part first: the same lock order as _reserve_database_budget.
    parts = [
        part
        for part in (reservation.global_reservation, reservation)
        if part is not None and part.database_reservation_id is not None
    ]
    if not parts:
        return
    with transaction.atomic():
        reservation_ids = [part.database_reservation_id for part in parts]
        if not PublicAssistantTokenReservation.objects.filter(pk__in=reservation_ids).exists():
            return
        # Every database path locks budget rows before reservation rows. This
        # keeps settlement compatible with reserve and with the cascading
        # cleanup.
        states = {
            part.actor_key: PublicAssistantTokenBudget.objects.select_for_update().filter(pk=part.actor_key).first()
            for part in parts
        }
        now = timezone.now()
        final_tokens = 0 if actual_tokens is None else max(0, int(actual_tokens))
        for part in parts:
            state = states[part.actor_key]
            if state is None:
                continue
            charged = (
                PublicAssistantTokenReservation.objects.select_for_update()
                .filter(pk=part.database_reservation_id, budget_id=part.actor_key)
                .first()
            )
            if charged is None:
                continue
            if state.window_id == charged.window_id and state.window_expires_at > now:
                state.tokens_used = max(0, state.tokens_used + final_tokens - charged.reserved_tokens)
                state.save(update_fields=["tokens_used"])
            charged.delete()


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


def _record_database_usage(actor_key: str, tokens: int, window_seconds: int) -> None:
    with transaction.atomic():
        state = _locked_database_budget(actor_key, window_seconds=window_seconds)
        state.tokens_used += tokens
        state.save(update_fields=["window_id", "tokens_used", "window_expires_at"])


def purge_expired_public_assistant_budgets(*, batch_size: int = 1000) -> int:
    """Delete one bounded batch of expired database counters and reservations."""
    batch_size = max(1, int(batch_size))
    cutoff = timezone.now()
    with transaction.atomic():
        # Skip rows currently being reset/reserved. Rows locked here cannot be
        # reactivated between the expiry check and the cascading delete.
        expired_hashes = list(
            PublicAssistantTokenBudget.objects.select_for_update(skip_locked=True)
            .filter(window_expires_at__lte=cutoff)
            .order_by("window_expires_at")
            .values_list("pk", flat=True)[:batch_size]
        )
        if not expired_hashes:
            return 0
        _deleted_total, deleted_by_model = PublicAssistantTokenBudget.objects.filter(
            pk__in=expired_hashes,
            window_expires_at__lte=cutoff,
        ).delete()
        return int(deleted_by_model.get(PublicAssistantTokenBudget._meta.label, 0))


def _reserve_cache_budget(
    actor_key: str,
    *,
    amount: int,
    limit: int,
    window_seconds: int,
) -> BudgetReservation | None:
    """Reserve against ONE counter in Redis, or in the opt-in local cache."""
    logical_budget_key = budget_key(actor_key)
    logical_window_key = _budget_window_key(actor_key)
    logical_reservation_key = _reservation_key()
    proposed_window_id = _new_window_id()
    redis_client = _shared_redis_client()
    if redis_client is not None:
        redis_budget_key = cache.make_key(logical_budget_key)
        redis_window_key = cache.make_key(logical_window_key)
        redis_reservation_key = cache.make_key(logical_reservation_key)
        try:
            result = int(
                redis_client.eval(
                    _RESERVE_SCRIPT,
                    3,
                    redis_budget_key,
                    redis_window_key,
                    redis_reservation_key,
                    amount,
                    limit,
                    window_seconds * 1000,
                    proposed_window_id,
                )
            )
        except Exception as exc:
            raise BudgetBackendUnavailable("Shared assistant budget is unavailable.") from exc
        if result < 0:
            return None
        return BudgetReservation(
            budget_cache_key=redis_budget_key,
            window_cache_key=redis_window_key,
            reservation_cache_key=redis_reservation_key,
            reserved_tokens=amount,
            window_seconds=window_seconds,
            shared_redis=True,
            actor_key=actor_key,
        )

    # Explicit test/development-only fallback; production never enables it.
    with _LOCAL_RESERVATION_LOCK:
        current = int(cache.get(logical_budget_key, 0) or 0)
        if limit > 0 and current + amount > limit:
            return None
        created = cache.add(logical_budget_key, 0, timeout=window_seconds)
        if created:
            window_id = proposed_window_id
            cache.set(logical_window_key, window_id, timeout=window_seconds)
        else:
            window_id = cache.get(logical_window_key)
            if not window_id:
                window_id = proposed_window_id
                cache.set(logical_window_key, window_id, timeout=window_seconds)
        try:
            cache.incr(logical_budget_key, amount)
        except ValueError:
            # The prior counter expired after it was read. This is a fresh
            # window, so do not carry the expired window's usage forward.
            cache.set(logical_budget_key, amount, timeout=window_seconds)
            window_id = proposed_window_id
            cache.set(logical_window_key, window_id, timeout=window_seconds)
        cache.set(
            logical_reservation_key,
            {"amount": amount, "window_id": window_id},
            timeout=window_seconds,
        )
    return BudgetReservation(
        budget_cache_key=logical_budget_key,
        window_cache_key=logical_window_key,
        reservation_cache_key=logical_reservation_key,
        reserved_tokens=amount,
        window_seconds=window_seconds,
        shared_redis=False,
        actor_key=actor_key,
    )


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

    # Redis / local cache: two single-counter reservations. Each one is atomic,
    # and the global one is given back if the actor's does not fit, so neither
    # budget can be overspent (a concurrent request may at worst be refused
    # while the first reservation is being returned). Production has no Redis
    # and always takes the single-transaction database path above.
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


def _settle_cache_reservation(reservation: BudgetReservation, *, actual_tokens: int | None) -> None:
    """Settle ONE Redis / local-cache reservation. ``None`` releases it in full."""
    if reservation.shared_redis:
        try:
            if actual_tokens is None:
                _shared_redis_client().eval(
                    _RELEASE_SCRIPT,
                    3,
                    reservation.budget_cache_key,
                    reservation.window_cache_key,
                    reservation.reservation_cache_key,
                )
            else:
                _shared_redis_client().eval(
                    _RECONCILE_SCRIPT,
                    3,
                    reservation.budget_cache_key,
                    reservation.window_cache_key,
                    reservation.reservation_cache_key,
                    actual_tokens,
                )
        except Exception as exc:
            action = "release" if actual_tokens is None else "reconcile"
            raise BudgetBackendUnavailable(f"Could not {action} assistant usage.") from exc
        return
    with _LOCAL_RESERVATION_LOCK:
        reservation_state = cache.get(reservation.reservation_cache_key)
        if not isinstance(reservation_state, dict):
            return
        reserved = int(reservation_state.get("amount", 0) or 0)
        window_id = reservation_state.get("window_id")
        active_window_id = cache.get(reservation.window_cache_key)
        if active_window_id != window_id or cache.get(reservation.budget_cache_key) is None:
            cache.delete(reservation.reservation_cache_key)
            return
        final_tokens = 0 if actual_tokens is None else actual_tokens
        try:
            current = cache.incr(reservation.budget_cache_key, final_tokens - reserved)
        except ValueError:
            cache.delete(reservation.reservation_cache_key)
            return
        if current < 0:
            try:
                cache.incr(reservation.budget_cache_key, -current)
            except ValueError:
                pass
        cache.delete(reservation.reservation_cache_key)


def _settle_cache_reservations(reservation: BudgetReservation, *, actual_tokens: int | None) -> None:
    """Settle the actor part and the global part; try both even if one fails."""
    failure: BudgetBackendUnavailable | None = None
    for part in (reservation, reservation.global_reservation):
        if part is None:
            continue
        try:
            _settle_cache_reservation(part, actual_tokens=actual_tokens)
        except BudgetBackendUnavailable as exc:
            failure = failure or exc
    if failure is not None:
        raise failure


def _release_cache_reservation_quietly(reservation: BudgetReservation) -> None:
    try:
        _settle_cache_reservation(reservation, actual_tokens=None)
    except BudgetBackendUnavailable:
        # The reservation key expires with its window; nothing else to do.
        logger.exception("Could not return an unused global assistant reservation")


# No single model call can cost this much (requests are capped far below it). A larger reported number is a
# provider or parsing fault, and storing it would overflow the counters, so it is treated as unreadable.
MAX_REPORTED_TOKENS = 10_000_000
_USAGE_KEYS = ("inputTokens", "outputTokens", "totalTokens")


def _token_count(value) -> int | None:
    """``value`` as a plausible token count, or ``None`` when it is not one (text, NaN, infinity, absurd size)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if 0 <= number <= MAX_REPORTED_TOKENS else None


def reported_total_tokens(usage):
    """The provider's ``totalTokens`` exactly as reported, for :func:`reconcile_budget`.

    A usage block that is not a mapping is passed through as is, so that reconciliation sees it is unreadable
    and settles the call at the reserved amount instead of charging nothing.
    """
    if isinstance(usage, Mapping):
        return usage.get("totalTokens") or 0
    return usage or 0


def sanitized_usage(usage) -> dict[str, int]:
    """The provider's usage block reduced to plausible token counts.

    This is what gets stored in the audit log and returned to the caller: the raw block is provider-controlled,
    and a non-finite number in it cannot be serialised as JSON.
    """
    if not isinstance(usage, Mapping):
        return {}
    clean = {}
    for key in _USAGE_KEYS:
        count = _token_count(usage.get(key))
        if count is not None:
            clean[key] = count
    return clean


def _reconciled_tokens(reservation: BudgetReservation, actual_tokens) -> int:
    """The provider's reported usage as a non-negative integer.

    The value comes from the provider's usage block. If it cannot be read as a
    plausible token count, the reservation is settled at the amount it reserved
    (estimated input plus the output cap): the budgets stay charged for the call,
    the reservation records are consumed, and the request is still answered.
    """
    if not actual_tokens and not isinstance(actual_tokens, bool):
        return 0
    try:
        number = int(actual_tokens)
    except (TypeError, ValueError, OverflowError):
        number = None
    if number is not None and number < 0:
        return 0
    if number is None or number > MAX_REPORTED_TOKENS or isinstance(actual_tokens, bool):
        logger.warning(
            "Unparsable provider token usage %.80r: charging the reserved %s tokens instead",
            actual_tokens,
            reservation.reserved_tokens,
        )
        return reservation.reserved_tokens
    return number


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
