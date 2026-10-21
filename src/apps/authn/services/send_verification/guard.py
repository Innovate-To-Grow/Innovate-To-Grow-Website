from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.authn.models import SendVerificationChallenge, SendVerificationRequest

from .challenges import check_challenge_usable
from .config import load_settings, require_ready
from .constants import (
    FIELD_CHALLENGE_ID,
    FIELD_PAYLOAD,
    FIELD_REQUEST_ID,
    MODE_OBSERVE,
    OP_PASSWORD_RESET_REQUEST_CODE,
    SMS_CHANNEL,
    SMS_OPERATIONS,
)
from .exceptions import (
    SendRequestConflict,
    SendVerificationConsumed,
    SendVerificationContextMismatch,
    SendVerificationInvalid,
    SendVerificationRequired,
)
from .metrics import emit
from .principal import principal_from_request, principals_match
from .proofs import check_signed_challenge, verify_payload
from .quotas import reserve_send_quotas


@dataclass
class ProtectedSend:
    record: SendVerificationRequest
    is_replay: bool
    skip_dispatch: bool = False


def _parse_uuid(value) -> UUID | None:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def extract_verification_fields(data) -> tuple[UUID | None, str, UUID | None]:
    if hasattr(data, "get") and not isinstance(data, dict):
        try:
            data = {key: data.get(key) for key in (FIELD_CHALLENGE_ID, FIELD_PAYLOAD, FIELD_REQUEST_ID)}
        except Exception:
            data = {}
    if not isinstance(data, dict):
        return None, "", None
    challenge_id = _parse_uuid(data.get(FIELD_CHALLENGE_ID))
    payload = data.get(FIELD_PAYLOAD) or ""
    if not isinstance(payload, str):
        payload = str(payload)
    request_id = _parse_uuid(data.get(FIELD_REQUEST_ID))
    return challenge_id, payload.strip(), request_id


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


def _mark_consumed(challenge, *, now) -> None:
    """Conditionally move the locked challenge from pending to consumed; it can be spent only once."""
    updated = SendVerificationChallenge.objects.filter(
        pk=challenge.pk,
        status=SendVerificationChallenge.Status.PENDING,
        expires_at__gt=now,
    ).update(
        status=SendVerificationChallenge.Status.CONSUMED,
        consumed_at=now,
        updated_at=now,
    )
    if not updated:
        raise SendVerificationConsumed()


def _reserve_for(record, *, config, now, refuse_spent_sms_budget) -> None:
    """Reserve the destination (and SMS) quotas for a new request and mark it reserved."""
    reserve_send_quotas(
        config=config,
        channel=record.channel,
        destination_kind=record.destination_kind,
        destination_normalized=record.destination_normalized,
        now=now,
        refuse_spent_sms_budget=refuse_spent_sms_budget,
    )
    record.quota_reserved = True
    record.reserved_at = now
    record.save(update_fields=["quota_reserved", "reserved_at", "updated_at"])


def _observe_without_proof(
    *,
    operation,
    destination_kind,
    destination_normalized,
    fingerprint,
    channel,
    principal_type,
    principal_key,
    refuse_spent_sms_budget=False,
) -> ProtectedSend:
    from uuid import uuid4

    config = load_settings()
    now = timezone.now()
    with transaction.atomic():
        reserve_send_quotas(
            config=config,
            channel=channel,
            destination_kind=destination_kind,
            destination_normalized=destination_normalized,
            now=now,
            refuse_spent_sms_budget=refuse_spent_sms_budget,
        )
        record = SendVerificationRequest.objects.create(
            request_id=uuid4(),
            operation=operation,
            channel=channel,
            destination_kind=destination_kind,
            destination_normalized=destination_normalized,
            principal_type=principal_type,
            principal_key=principal_key,
            request_fingerprint=fingerprint,
            status=SendVerificationRequest.Status.PENDING,
            quota_reserved=True,
            reserved_at=now,
            idempotency_expires_at=now + timedelta(seconds=config.idempotency_ttl_seconds),
        )
    return ProtectedSend(record=record, is_replay=False)


def _replay(existing: SendVerificationRequest) -> ProtectedSend:
    if existing.status in {
        SendVerificationRequest.Status.PROVIDER_ACCEPTED,
        SendVerificationRequest.Status.DEFINITELY_FAILED,
        SendVerificationRequest.Status.UNKNOWN,
    }:
        emit("request_replay", request_id=str(existing.request_id), status=existing.status)
        return ProtectedSend(record=existing, is_replay=True)
    if existing.status == SendVerificationRequest.Status.SENDING:
        return ProtectedSend(record=existing, is_replay=True)
    return ProtectedSend(record=existing, is_replay=False)


def claim_for_dispatch(record: SendVerificationRequest) -> bool:
    return bool(
        SendVerificationRequest.objects.filter(
            pk=record.pk,
            status=SendVerificationRequest.Status.PENDING,
        ).update(status=SendVerificationRequest.Status.SENDING, updated_at=timezone.now())
    )


def finalize_send_request(
    record: SendVerificationRequest,
    *,
    status: str,
    result_payload: dict,
    http_status: int,
    client_error_code: str = "",
    otp_challenge_id: str = "",
    provider_message_id: str = "",
) -> SendVerificationRequest:
    now = timezone.now()
    SendVerificationRequest.objects.filter(pk=record.pk, status=SendVerificationRequest.Status.SENDING).update(
        status=status,
        result_payload=result_payload,
        http_status=http_status,
        client_error_code=client_error_code,
        otp_challenge_id=otp_challenge_id or record.otp_challenge_id,
        provider_message_id=provider_message_id or record.provider_message_id,
        updated_at=now,
    )
    record.refresh_from_db()
    emit("send_finalized", request_id=str(record.request_id), status=status, http_status=http_status)
    return record


def lookup_request(request, request_id: UUID) -> SendVerificationRequest:
    record = SendVerificationRequest.objects.filter(request_id=request_id).first()
    if record is None:
        raise SendVerificationInvalid("Send request was not found.")
    from .principal import authenticate_for_operation

    authenticate_for_operation(request, record.operation)
    principal_type, principal_key = principal_from_request(request, operation=record.operation)
    if record is None or not principals_match(
        record.principal_type, record.principal_key, principal_type, principal_key
    ):
        raise SendVerificationInvalid("Send request was not found.")
    return record
