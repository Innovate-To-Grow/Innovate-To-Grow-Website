"""Redis counters (atomic Lua scripts), or the opt-in local cache for tests and development."""

import threading

from django.conf import settings
from django.core.cache import cache

from .limits import (
    BudgetBackendUnavailable,
    BudgetReservation,
    _budget_window_key,
    _new_window_id,
    _reservation_key,
    budget_key,
    logger,
)
from .redis_scripts import _RECONCILE_SCRIPT, _RELEASE_SCRIPT, _RESERVE_SCRIPT

_LOCAL_RESERVATION_LOCK = threading.Lock()


def _shared_redis_client():
    try:
        from django_redis import get_redis_connection

        return get_redis_connection("default")
    except Exception as exc:
        if getattr(settings, "PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET", False):
            return None
        raise BudgetBackendUnavailable("Shared assistant budget is unavailable.") from exc


def _reserve_redis(redis_client, actor_key: str, keys, *, amount: int, limit: int, window_seconds: int, window_id: str):
    """Run the atomic reservation script against the shared Redis counter."""
    redis_budget_key, redis_window_key, redis_reservation_key = (cache.make_key(key) for key in keys)
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
                window_id,
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


def _reserve_local(actor_key: str, keys, *, amount: int, limit: int, window_seconds: int, proposed_window_id: str):
    """Explicit test/development-only fallback on the local cache; production never enables it."""
    logical_budget_key, logical_window_key, logical_reservation_key = keys
    with _LOCAL_RESERVATION_LOCK:
        current = int(cache.get(logical_budget_key, 0) or 0)
        if limit > 0 and current + amount > limit:
            return None
        created = cache.add(logical_budget_key, 0, timeout=window_seconds)
        window_id = None if created else cache.get(logical_window_key)
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


def _reserve_cache_budget(
    actor_key: str,
    *,
    amount: int,
    limit: int,
    window_seconds: int,
) -> BudgetReservation | None:
    """Reserve against ONE counter in Redis, or in the opt-in local cache."""
    keys = (budget_key(actor_key), _budget_window_key(actor_key), _reservation_key())
    proposed_window_id = _new_window_id()
    redis_client = _shared_redis_client()
    if redis_client is not None:
        return _reserve_redis(
            redis_client,
            actor_key,
            keys,
            amount=amount,
            limit=limit,
            window_seconds=window_seconds,
            window_id=proposed_window_id,
        )
    return _reserve_local(
        actor_key,
        keys,
        amount=amount,
        limit=limit,
        window_seconds=window_seconds,
        proposed_window_id=proposed_window_id,
    )


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
