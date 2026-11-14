"""``consume_and_reserve``: check a send's proof, spend its challenge and reserve its quotas in one transaction, or
replay the request it repeats."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.authn.models import SendVerificationChallenge, SendVerificationRequest

from ..proofs.challenges import check_challenge_usable
from ..proofs.fields import extract_verification_fields
from ..proofs.principal import principal_from_request, principals_match
from ..proofs.verification import check_signed_challenge, verify_payload
from ..rules.config import load_settings, require_ready
from ..rules.constants import MODE_OBSERVE, OP_PASSWORD_RESET_REQUEST_CODE, SMS_CHANNEL, SMS_OPERATIONS
from ..rules.exceptions import (
    SendRequestConflict,
    SendVerificationContextMismatch,
    SendVerificationInvalid,
    SendVerificationRequired,
)
from ..rules.metrics import emit
from .requests import ProtectedSend, _replay
from .reservation import _mark_consumed, _observe_without_proof, _reserve_for


def _load_existing_request(
    request_id: UUID,
    principal_type: str,
    principal_key: str,
    fingerprint: str,
    *,
    operation: str,
    channel: str,
    destination_kind: str,
    destination_normalized: str,
):
    existing = SendVerificationRequest.objects.select_for_update().filter(request_id=request_id).first()
    if existing is None:
        return None
    if not principals_match(existing.principal_type, existing.principal_key, principal_type, principal_key):
        raise SendVerificationContextMismatch()
    if (
        existing.request_fingerprint != fingerprint
        or existing.operation != operation
        or existing.channel != channel
        or existing.destination_kind != destination_kind
        or existing.destination_normalized != destination_normalized
    ):
        raise SendRequestConflict()
    return existing


def consume_and_reserve(
    request,
    *,
    operation: str,
    destination_kind: str,
    destination_normalized: str,
    fingerprint: str,
    channel: str,
) -> ProtectedSend:
    raw = getattr(request, "data", None)
    if raw is None:
        raw = getattr(request, "POST", {}) or {}
    challenge_id, payload, request_id = extract_verification_fields(raw)
    principal_type, principal_key = principal_from_request(request, operation=operation)
    config = load_settings()
    # The SMS daily budget is reserved where the SMS is dispatched (``reserve_sms_dispatch``), not here. A request
    # that is certain to send one is still refused up front when the budget is already spent, before its proof and
    # cooldown are used. Password reset is not: it sends only when the number has an account, so its answer must not
    # depend on the budget (it answers its neutral 202 and the SMS is quietly not sent).
    refuse_spent_sms_budget = channel == SMS_CHANNEL and operation != OP_PASSWORD_RESET_REQUEST_CODE
    context = {
        "operation": operation,
        "channel": channel,
        "destination_kind": destination_kind,
        "destination_normalized": destination_normalized,
    }

    if config.mode == MODE_OBSERVE and not (challenge_id and payload and request_id):
        emit("observe_missing_proof", operation=operation, destination=destination_normalized)
        # Observation still reserves destination quotas so rollout does not
        # silently drop abuse controls. A synthetic request id is not reused.
        return _observe_without_proof(
            fingerprint=fingerprint,
            principal_type=principal_type,
            principal_key=principal_key,
            refuse_spent_sms_budget=refuse_spent_sms_budget,
            **context,
        )

    config = require_ready(for_sms=channel == SMS_CHANNEL or operation in SMS_OPERATIONS)
    if not challenge_id or not payload or not request_id:
        raise SendVerificationRequired()

    try:
        return _consume_transaction(
            request_id=request_id,
            challenge_id=challenge_id,
            payload=payload,
            principal_type=principal_type,
            principal_key=principal_key,
            fingerprint=fingerprint,
            config=config,
            context=context,
            refuse_spent_sms_budget=refuse_spent_sms_budget,
        )
    except IntegrityError as exc:
        return _replay_competing_request(exc, request_id, principal_type, principal_key, fingerprint, context)


def _replay_competing_request(exc, request_id, principal_type, principal_key, fingerprint, context) -> ProtectedSend:
    # The entire attempted consumption/reservation has rolled back before
    # reading a competing winner. Never query inside a broken transaction.
    with transaction.atomic():
        existing = _load_existing_request(request_id, principal_type, principal_key, fingerprint, **context)
        if existing is None:
            raise SendRequestConflict() from exc
        return _replay(existing)


def _consume_transaction(
    *,
    request_id,
    challenge_id,
    payload,
    principal_type,
    principal_key,
    fingerprint,
    config,
    context: dict,
    refuse_spent_sms_budget=False,
):
    """Spend the challenge and create the reserved request in one transaction (or replay a finished one).

    ``context`` holds the send's ``operation``, ``channel``, ``destination_kind`` and ``destination_normalized``.
    """
    with transaction.atomic():
        existing = _load_existing_request(request_id, principal_type, principal_key, fingerprint, **context)
        if existing is not None:
            return _replay(existing)

        challenge = SendVerificationChallenge.objects.select_for_update().filter(pk=challenge_id).first()
        if challenge is None:
            raise SendVerificationInvalid()
        # Another transaction may have completed this exact request while we
        # waited for its challenge lock.
        existing = _load_existing_request(request_id, principal_type, principal_key, fingerprint, **context)
        if existing is not None:
            return _replay(existing)
        now = timezone.now()
        check_challenge_usable(
            challenge, now=now, principal_type=principal_type, principal_key=principal_key, **context
        )
        verify_payload(payload, config, algorithm=challenge.algorithm, cost=challenge.cost)
        check_signed_challenge(payload, challenge, operation=context["operation"])
        _mark_consumed(challenge, now=now)

        record = SendVerificationRequest.objects.create(
            request_id=request_id,
            challenge=challenge,
            principal_type=principal_type,
            principal_key=principal_key,
            request_fingerprint=fingerprint,
            status=SendVerificationRequest.Status.PENDING,
            quota_reserved=False,
            idempotency_expires_at=now + timedelta(seconds=config.idempotency_ttl_seconds),
            **context,
        )
        _reserve_for(record, config=config, now=now, refuse_spent_sms_budget=refuse_spent_sms_budget)

    emit(
        "challenge_consumed",
        operation=context["operation"],
        request_id=str(request_id),
        destination=context["destination_normalized"],
    )
    return ProtectedSend(record=record, is_replay=False)
