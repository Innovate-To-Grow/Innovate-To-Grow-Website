"""Reserving a request's tokens against its actor's and its feature's budgets, and settling the reservation."""

from dataclasses import replace

from django.conf import settings

from .cache_store import _release_cache_reservation_quietly, _reserve_cache_budget, _settle_cache_reservations
from .database_store import _reserve_database_budget, _settle_database_reservation
from .limits import (
    _DEFAULT_WINDOW_SECONDS,
    GLOBAL_WINDOW_SECONDS,
    BudgetBackendUnavailable,
    BudgetReservation,
    _warn_global_budget_exhausted,
    global_budget_key,
)
from .usage import _reconciled_tokens


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
