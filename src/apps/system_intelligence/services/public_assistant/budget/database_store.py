"""Transactional PostgreSQL counters: the authoritative store when Redis is not configured.

Every reservation charges row-locked counters and records a reservation row in the
same transaction; settlement consumes that row exactly once.
"""

from dataclasses import replace
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.system_intelligence.models import PublicAssistantTokenBudget, PublicAssistantTokenReservation

from .limits import (
    GLOBAL_WINDOW_SECONDS,
    BudgetReservation,
    _budget_window_key,
    _GlobalBudgetExhausted,
    _new_window_id,
    _warn_global_budget_exhausted,
    budget_key,
    global_budget_key,
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


def _locked_global_state(feature, amount: int, global_limit: int):
    """Lock ``feature``'s global row; raise ``_GlobalBudgetExhausted`` when ``amount`` does not fit."""
    global_state = _locked_database_budget(global_budget_key(feature), window_seconds=GLOBAL_WINDOW_SECONDS)
    if global_state.tokens_used + amount > global_limit:
        raise _GlobalBudgetExhausted
    return global_state


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
            # The global row is locked first (see LOCK ORDER above).
            global_state = _locked_global_state(feature, amount, global_limit) if global_limit is not None else None
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
