"""Per-IP token budgeting for the public assistant.

The budget is tracked entirely in Django's cache (LocMem in dev, Redis in
prod) as a rolling counter keyed on a salted SHA-256 hash of the client IP.
Only the hash is ever stored -- never the raw IP.
"""

import hashlib
import threading
import uuid
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache

# Fallback window if a non-positive value is configured: in Django, a cache
# timeout of 0 means "expire immediately / do not store", which would silently
# disable the budget. Clamp to a 1-day rolling window instead.
_DEFAULT_WINDOW_SECONDS = 86400
_LOCAL_RESERVATION_LOCK = threading.Lock()


class BudgetBackendUnavailable(RuntimeError):
    """Raised when the shared Redis budget cannot be reached."""


@dataclass(frozen=True)
class BudgetReservation:
    budget_cache_key: str
    window_cache_key: str
    reservation_cache_key: str
    reserved_tokens: int
    window_seconds: int
    shared_redis: bool


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
    """Return the originating client IP, honouring NUM_PROXIES trusted hops.

    Mirrors ``apps.cms.views.analytics.PageViewCreateView._get_client_ip``:
    X-Forwarded-For is appended-to by each proxy. With ``NUM_PROXIES = N`` the
    rightmost N entries are trusted proxy hops and the Nth-from-right entry is
    the actual client. Without NUM_PROXIES (dev / tests) fall back to the
    leftmost entry, then to REMOTE_ADDR.
    """
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            num_proxies = getattr(settings, "NUM_PROXIES", None)
            if num_proxies:
                index = max(0, len(parts) - num_proxies)
                return parts[index]
            return parts[0]
    return request.META.get("REMOTE_ADDR")


def hash_ip(ip: str) -> str:
    """Salted SHA-256 hash of an IP. Salt with SECRET_KEY (repo convention)."""
    return hashlib.sha256(f"{settings.SECRET_KEY}:{ip}".encode()).hexdigest()


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
    return cache.get(budget_key(ip_hash), 0)


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
