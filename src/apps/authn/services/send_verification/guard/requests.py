"""A protected send request once its proof was consumed: the handle the guard returns, the replay of a repeated
request, the dispatch claim, the final outcome and the status lookup."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from django.utils import timezone

from apps.authn.models import SendVerificationRequest

from ..proofs.principal import principal_from_request, principals_match
from ..rules.exceptions import SendVerificationInvalid
from ..rules.metrics import emit


@dataclass
class ProtectedSend:
    record: SendVerificationRequest
    is_replay: bool
    skip_dispatch: bool = False


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
    from ..proofs.principal import authenticate_for_operation

    authenticate_for_operation(request, record.operation)
    principal_type, principal_key = principal_from_request(request, operation=record.operation)
    if record is None or not principals_match(
        record.principal_type, record.principal_key, principal_type, principal_key
    ):
        raise SendVerificationInvalid("Send request was not found.")
    return record
