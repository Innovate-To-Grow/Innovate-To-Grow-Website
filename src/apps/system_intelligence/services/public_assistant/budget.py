"""Per-IP token budgeting for the public assistant.

Redis is used when configured. Production environments without Redis use a
transactional database counter, while tests/development may explicitly opt in
to the local cache fallback. Only a salted IP hash is stored -- never the raw
IP.
"""

import threading
import uuid
from dataclasses import dataclass
from datetime import timedelta

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

# Fallback window if a non-positive value is configured: in Django, a cache
# timeout of 0 means "expire immediately / do not store", which would silently
# disable the budget. Clamp to a 1-day rolling window instead.
_DEFAULT_WINDOW_SECONDS = 86400
_LOCAL_RESERVATION_LOCK = threading.Lock()


class BudgetBackendUnavailable(RuntimeError):
    """Raised when the shared budget backend cannot be reached."""


@dataclass(frozen=True)
class BudgetReservation:
    budget_cache_key: str
    window_cache_key: str
    reservation_cache_key: str
    reserved_tokens: int
    window_seconds: int
    shared_redis: bool
    database: bool = False
    ip_hash: str = ""
    window_id: int = 0
    database_reservation_id: uuid.UUID | None = None


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
    """Return the originating client IP. Delegates to the shared apps.core helper."""
    return _client_ip(request)


def hash_ip(ip: str) -> str:
    """Salted SHA-256 hash of an IP. Delegates to the shared apps.core helper."""
    return _hash_ip(ip)


def budget_key(ip_hash: str) -> str:
    return f"assistant:tokens:{ip_hash}"


def _budget_window_key(ip_hash: str) -> str:
    return f"assistant:tokens-window:{ip_hash}"


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


def _locked_database_budget(ip_hash: str, *, window_seconds: int) -> PublicAssistantTokenBudget:
    initial_now = timezone.now()
    state, _created = PublicAssistantTokenBudget.objects.select_for_update().get_or_create(
        ip_hash=ip_hash,
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


def _reserve_database_budget(
    ip_hash: str,
    *,
    amount: int,
    limit: int,
    window_seconds: int,
) -> BudgetReservation | None:
    # Match the Redis semantics: an impossible request must not create and
    # anchor an otherwise-empty fixed budget window.
    if limit > 0 and amount > limit:
        return None
    with transaction.atomic():
        state = _locked_database_budget(ip_hash, window_seconds=window_seconds)
        if limit > 0 and state.tokens_used + amount > limit:
            return None
        state.tokens_used += amount
        state.save(update_fields=["window_id", "tokens_used", "window_expires_at"])
        database_reservation = PublicAssistantTokenReservation.objects.create(
            budget=state,
            window_id=state.window_id,
            reserved_tokens=amount,
        )
    return BudgetReservation(
        budget_cache_key=budget_key(ip_hash),
        window_cache_key=_budget_window_key(ip_hash),
        reservation_cache_key="",
        reserved_tokens=amount,
        window_seconds=window_seconds,
        shared_redis=False,
        database=True,
        ip_hash=ip_hash,
        window_id=state.window_id,
        database_reservation_id=database_reservation.pk,
    )


def _settle_database_reservation(
    reservation: BudgetReservation,
    *,
    actual_tokens: int | None,
) -> None:
    """Consume a database reservation exactly once.

    ``actual_tokens=None`` releases the full reservation. A successful
    reconcile stores the provider's actual usage. The reservation row is
    deleted in the same transaction as the counter change, so repeats and
    cross-worker retries are harmless.
    """
    if reservation.database_reservation_id is None:
        return
    with transaction.atomic():
        reservation_snapshot = (
            PublicAssistantTokenReservation.objects.filter(pk=reservation.database_reservation_id)
            .values("budget_id", "window_id")
            .first()
        )
        if reservation_snapshot is None:
            return
        # Every database path locks in budget -> reservation order. This keeps
        # settlement compatible with reserve and with the cascading cleanup.
        state = (
            PublicAssistantTokenBudget.objects.select_for_update().filter(pk=reservation_snapshot["budget_id"]).first()
        )
        if state is None:
            return
        charged = (
            PublicAssistantTokenReservation.objects.select_for_update()
            .filter(pk=reservation.database_reservation_id)
            .filter(
                budget_id=reservation_snapshot["budget_id"],
                window_id=reservation_snapshot["window_id"],
            )
            .first()
        )
        if charged is None:
            return
        now = timezone.now()
        if state.window_id == charged.window_id and state.window_expires_at > now:
            final_tokens = 0 if actual_tokens is None else max(0, int(actual_tokens))
            state.tokens_used = max(0, state.tokens_used + final_tokens - charged.reserved_tokens)
            state.save(update_fields=["tokens_used"])
        charged.delete()


def _database_tokens_used(ip_hash: str) -> int:
    value = (
        PublicAssistantTokenBudget.objects.filter(
            ip_hash=ip_hash,
            window_expires_at__gt=timezone.now(),
        )
        .values_list("tokens_used", flat=True)
        .first()
    )
    return int(value or 0)


def _record_database_usage(ip_hash: str, tokens: int, window_seconds: int) -> None:
    with transaction.atomic():
        state = _locked_database_budget(ip_hash, window_seconds=window_seconds)
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


def reserve_budget(
    ip_hash: str,
    *,
    estimated_input_tokens: int,
    maximum_output_tokens: int,
    limit: int,
    window_seconds: int,
) -> BudgetReservation | None:
    """Atomically reserve estimated input plus the maximum possible output."""
    amount = max(0, estimated_input_tokens) + max(0, maximum_output_tokens)
    window_seconds = window_seconds if window_seconds > 0 else _DEFAULT_WINDOW_SECONDS
    logical_budget_key = budget_key(ip_hash)
    logical_window_key = _budget_window_key(ip_hash)
    logical_reservation_key = _reservation_key()
    proposed_window_id = _new_window_id()
    if _database_budget_enabled():
        try:
            return _reserve_database_budget(
                ip_hash,
                amount=amount,
                limit=limit,
                window_seconds=window_seconds,
            )
        except Exception as exc:
            raise BudgetBackendUnavailable("Shared database assistant budget is unavailable.") from exc
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
    )


def reconcile_budget(reservation: BudgetReservation, actual_tokens: int) -> None:
    actual_tokens = max(0, int(actual_tokens or 0))
    if reservation.database:
        try:
            _settle_database_reservation(reservation, actual_tokens=actual_tokens)
        except Exception as exc:
            raise BudgetBackendUnavailable("Could not reconcile database assistant usage.") from exc
        return
    if reservation.shared_redis:
        try:
            _shared_redis_client().eval(
                _RECONCILE_SCRIPT,
                3,
                reservation.budget_cache_key,
                reservation.window_cache_key,
                reservation.reservation_cache_key,
                actual_tokens,
            )
        except Exception as exc:
            raise BudgetBackendUnavailable("Could not reconcile assistant usage.") from exc
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
        try:
            current = cache.incr(
                reservation.budget_cache_key,
                actual_tokens - reserved,
            )
        except ValueError:
            cache.delete(reservation.reservation_cache_key)
            return
        if current < 0:
            try:
                cache.incr(reservation.budget_cache_key, -current)
            except ValueError:
                pass
        cache.delete(reservation.reservation_cache_key)


def release_budget(reservation: BudgetReservation) -> None:
    if reservation.database:
        try:
            _settle_database_reservation(reservation, actual_tokens=None)
        except Exception as exc:
            raise BudgetBackendUnavailable("Could not release database assistant usage.") from exc
        return
    if reservation.shared_redis:
        try:
            _shared_redis_client().eval(
                _RELEASE_SCRIPT,
                3,
                reservation.budget_cache_key,
                reservation.window_cache_key,
                reservation.reservation_cache_key,
            )
        except Exception as exc:
            raise BudgetBackendUnavailable("Could not release assistant usage.") from exc
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
        try:
            current = cache.incr(reservation.budget_cache_key, -reserved)
        except ValueError:
            cache.delete(reservation.reservation_cache_key)
            return
        if current < 0:
            try:
                cache.incr(reservation.budget_cache_key, -current)
            except ValueError:
                pass
        cache.delete(reservation.reservation_cache_key)


def tokens_used(ip_hash: str) -> int:
    if _database_budget_enabled():
        return _database_tokens_used(ip_hash)
    return int(cache.get(budget_key(ip_hash), 0) or 0)


def check_budget(ip_hash: str, limit: int) -> bool:
    """True if the IP may spend more tokens. limit <= 0 means unlimited."""
    if limit <= 0:
        return True
    return tokens_used(ip_hash) < limit


def record_usage(ip_hash: str, tokens: int, window_seconds: int) -> None:
    """Add ``tokens`` to the rolling per-IP counter, creating it if absent."""
    if tokens <= 0:
        return
    # A timeout of 0 (or negative) makes Django's cache discard the write
    # immediately, silently disabling the budget; clamp to a sane window.
    if window_seconds <= 0:
        window_seconds = _DEFAULT_WINDOW_SECONDS
    if _database_budget_enabled():
        _record_database_usage(ip_hash, tokens, window_seconds)
        return
    key = budget_key(ip_hash)
    # add() is a no-op if the key already exists, so the window is set on the
    # first write of the period and the counter rolls over when it expires.
    created = cache.add(key, 0, timeout=window_seconds)
    if created:
        cache.set(_budget_window_key(ip_hash), _new_window_id(), timeout=window_seconds)
    try:
        cache.incr(key, tokens)
    except ValueError:
        # The key expired between add() and incr(); re-seed and retry once.
        created = cache.add(key, 0, timeout=window_seconds)
        if created:
            cache.set(_budget_window_key(ip_hash), _new_window_id(), timeout=window_seconds)
        try:
            cache.incr(key, tokens)
        except ValueError:
            cache.set(key, tokens, timeout=window_seconds)
            cache.set(_budget_window_key(ip_hash), _new_window_id(), timeout=window_seconds)
