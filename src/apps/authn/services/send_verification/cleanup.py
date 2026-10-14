"""Retention cleanup for send-verification rows and expired sessions, in bounded batches.

Challenge issuance is not limited per client IP, so these tables can grow quickly between runs. Every step works
through at most ``batch_size`` primary keys at a time: memory, statement size and transaction length stay bounded
whatever the backlog, and each batch commits on its own. The background worker runs this hourly; the
``cleanup_send_verification`` command runs the same code on demand.

Every loop takes an optional ``should_stop`` callable and asks it before each batch. Once it returns true the loop
ends: the batch in flight has already committed, nothing is left half done, and the next run carries on from the
rows that remain. The worker passes its shutdown flag, so a large backlog cannot hold up a stop request.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from importlib import import_module

from django.conf import settings
from django.db import router, transaction
from django.utils import timezone

from apps.authn.models import SendVerificationChallenge, SendVerificationRequest

from .config import load_settings
from .metrics import emit

DEFAULT_BATCH_SIZE = 1000


StopCheck = Callable[[], bool] | None


def _next_batch(queryset, batch_size: int, should_stop: StopCheck = None) -> list:
    """The next ``batch_size`` primary keys of ``queryset``; empty (which ends the caller's loop) once stopping."""
    if should_stop is not None and should_stop():
        return []
    return list(queryset.order_by().values_list("pk", flat=True)[:batch_size])


def _expire_pending_challenges(*, now, batch_size: int, should_stop: StopCheck = None) -> int:
    pending = SendVerificationChallenge.objects.filter(
        status=SendVerificationChallenge.Status.PENDING,
        expires_at__lte=now,
    )
    total = 0
    while batch := _next_batch(pending, batch_size, should_stop):
        # Re-check the status: a row consumed since the SELECT stays consumed. Either way it no longer matches
        # ``pending``, so the loop cannot see the same key twice.
        total += SendVerificationChallenge.objects.filter(
            pk__in=batch,
            status=SendVerificationChallenge.Status.PENDING,
        ).update(status=SendVerificationChallenge.Status.EXPIRED, updated_at=now)
    return total


def _delete_old_challenges(*, cutoff, batch_size: int, should_stop: StopCheck = None) -> int:
    old = SendVerificationChallenge.objects.filter(expires_at__lt=cutoff)
    total = 0
    while batch := _next_batch(old, batch_size, should_stop):
        with transaction.atomic():
            # ``SendVerificationRequest.challenge`` (SET_NULL) is the only relation to this model: clear it for the
            # whole batch in one UPDATE, then delete the batch with one DELETE. A plain ``.delete()`` would load every
            # row into memory for the collector. A test pins the relation set, so a new relation fails loudly.
            SendVerificationRequest.objects.filter(challenge_id__in=batch).update(challenge=None)
            total += SendVerificationChallenge.objects.filter(pk__in=batch)._raw_delete(
                router.db_for_write(SendVerificationChallenge)
            )
    return total


def _delete_old_requests(*, cutoff, batch_size: int, should_stop: StopCheck = None) -> int:
    old = SendVerificationRequest.objects.filter(idempotency_expires_at__lt=cutoff)
    total = 0
    while batch := _next_batch(old, batch_size, should_stop):
        # Nothing references a send request (a test pins that), so the batch goes in one DELETE. A plain ``.delete()``
        # would not: django-ckeditor-5 connects a ``pre_delete`` receiver for every model, which makes the collector
        # load the rows and delete them 100 at a time.
        total += SendVerificationRequest.objects.filter(pk__in=batch)._raw_delete(
            router.db_for_write(SendVerificationRequest)
        )
    return total


def cleanup_expired_records(
    *, now=None, batch_size: int = DEFAULT_BATCH_SIZE, should_stop: StopCheck = None
) -> dict[str, int]:
    """Expire overdue pending challenges, then delete challenges and send requests past the retention window.

    With ``should_stop``, the counts are those of the batches that ran before it returned true.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1.")
    config = load_settings()
    now = now or timezone.now()
    cutoff = now - timedelta(days=config.retention_days)
    expired_challenges = _expire_pending_challenges(now=now, batch_size=batch_size, should_stop=should_stop)
    deleted_challenges = _delete_old_challenges(cutoff=cutoff, batch_size=batch_size, should_stop=should_stop)
    deleted_requests = _delete_old_requests(cutoff=cutoff, batch_size=batch_size, should_stop=should_stop)
    emit(
        "cleanup",
        expired_challenges=expired_challenges,
        deleted_challenges=deleted_challenges,
        deleted_requests=deleted_requests,
    )
    return {
        "expired_challenges": expired_challenges,
        "deleted_challenges": deleted_challenges,
        "deleted_requests": deleted_requests,
    }


def clear_expired_sessions(
    *, now=None, batch_size: int = DEFAULT_BATCH_SIZE, should_stop: StopCheck = None
) -> int | None:
    """``clearsessions`` for the configured ``SESSION_ENGINE``, deleting database-backed sessions in batches.

    Anonymous send-verification requests save a session for a caller that has none (``principal_from_request``), so
    the session table grows with that (IP-unthrottled) traffic. For a database-backed store (``db``, ``cached_db`` and
    subclasses: anything exposing ``get_model_class``) this deletes the rows ``SessionStore.clear_expired()`` would,
    ``batch_size`` keys at a time, and returns the count. Any other engine gets its own ``clear_expired()`` (file
    cleanup; a no-op for cache and signed cookies) and ``None``, as the engine reports no count. ``should_stop``
    ends the batched delete early (see the module docstring).
    """
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1.")
    store = import_module(settings.SESSION_ENGINE).SessionStore
    get_model_class = getattr(store, "get_model_class", None)
    if get_model_class is None:
        try:
            store.clear_expired()
        except NotImplementedError:
            # Same outcome as ``clearsessions``: this engine cannot enumerate expired sessions.
            pass
        return None
    session_model = get_model_class()
    expired = session_model.objects.filter(expire_date__lt=now or timezone.now())
    total = 0
    while batch := _next_batch(expired, batch_size, should_stop):
        deleted, _ = session_model.objects.filter(pk__in=batch).delete()
        total += deleted
    return total
