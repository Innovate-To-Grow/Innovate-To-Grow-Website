from __future__ import annotations

import logging
from collections.abc import Callable

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response

from apps.authn.models import SendVerificationRequest

from .constants import OP_PASSWORD_RESET_REQUEST_CODE
from .exceptions import SendVerificationError
from .guard import claim_for_dispatch, consume_and_reserve, finalize_send_request
from .metrics import emit
from .outcomes import SendOutcome, delivery_context, failure_status, public_reset_payload

logger = logging.getLogger(__name__)


def verification_error_response(exc: SendVerificationError) -> Response:
    payload = {"code": exc.code, "detail": exc.detail}
    if exc.retry_after:
        payload["retry_after"] = exc.retry_after
    response = Response(payload, status=exc.http_status)
    if exc.retry_after:
        response["Retry-After"] = str(exc.retry_after)
    return response


def _reset_payload(record) -> dict:
    # Every outcome gets the same opaque public projection, even when a process
    # crashes before serializer.save can return its normal payload.
    return public_reset_payload(str(record.request_id))


def unknown_response(record) -> Response:
    return Response(
        {
            "code": "send_unknown",
            "detail": "The previous send request is still unresolved. Check your messages before requesting another code.",
            "request_id": str(record.request_id),
            "challenge_id": record.otp_challenge_id or None,
        },
        status=status.HTTP_409_CONFLICT,
    )


def replay_response(record: SendVerificationRequest) -> Response:
    if record.operation == OP_PASSWORD_RESET_REQUEST_CODE:
        return Response(_reset_payload(record), status=status.HTTP_202_ACCEPTED)
    if record.status in {
        SendVerificationRequest.Status.UNKNOWN,
        SendVerificationRequest.Status.SENDING,
        SendVerificationRequest.Status.PENDING,
    }:
        return unknown_response(record)
    payload = dict(record.result_payload or {})
    if record.client_error_code:
        payload.setdefault("code", record.client_error_code)
    return Response(payload, status=record.http_status)


def _finalize(record, outcome: SendOutcome):
    try:
        finalize_send_request(
            record,
            status=outcome.status,
            result_payload=outcome.payload,
            http_status=outcome.http_status,
            otp_challenge_id=outcome.otp_challenge_id,
            provider_message_id=outcome.provider_message_id,
            client_error_code=(
                "send_unknown"
                if outcome.status == SendVerificationRequest.Status.UNKNOWN
                else str(outcome.payload.get("code") or "")
            ),
        )
    except Exception:  # noqa: BLE001 - dispatch has happened; never authorize a retry.
        logger.exception("Unable to finalize protected send request %s", record.request_id)
        record.status = SendVerificationRequest.Status.SENDING
        if outcome.otp_challenge_id:
            record.otp_challenge_id = outcome.otp_challenge_id


def guarded_send(
    request,
    *,
    operation: str,
    destination_kind: str,
    destination_normalized: str,
    fingerprint: str,
    channel: str,
    perform: Callable[[], tuple[dict, int] | SendOutcome],
) -> Response:
    try:
        lease = consume_and_reserve(
            request,
            operation=operation,
            destination_kind=destination_kind,
            destination_normalized=destination_normalized,
            fingerprint=fingerprint,
            channel=channel,
        )
    except SendVerificationError as exc:
        emit("send_rejected", operation=operation, code=exc.code, destination=destination_normalized)
        return verification_error_response(exc)

    if lease.is_replay:
        return replay_response(lease.record)
    if not claim_for_dispatch(lease.record):
        lease.record.refresh_from_db()
        return replay_response(lease.record)
    lease.record.status = SendVerificationRequest.Status.SENDING

    try:
        with delivery_context(lease.record):
            result = perform()
        if isinstance(result, SendOutcome):
            outcome = result
        else:
            payload, http_status = result
            payload = payload if isinstance(payload, dict) else {"detail": payload}
            outcome = SendOutcome(
                payload,
                http_status,
                SendVerificationRequest.Status.PROVIDER_ACCEPTED
                if 200 <= http_status < 300
                else SendVerificationRequest.Status.UNKNOWN
                if http_status >= 500
                else SendVerificationRequest.Status.DEFINITELY_FAILED,
                str(payload.get("challenge_id") or ""),
            )
    except SendVerificationError as exc:
        outcome = SendOutcome(
            {"code": exc.code, "detail": exc.detail},
            exc.http_status,
            SendVerificationRequest.Status.DEFINITELY_FAILED,
        )
    except Exception as exc:  # noqa: BLE001
        from apps.authn.views.helpers import challenge_error_response

        try:
            mapped = (
                Response(exc.detail, status=exc.status_code)
                if isinstance(exc, APIException)
                else challenge_error_response(exc)
            )
            payload = mapped.data if isinstance(mapped.data, dict) else {"detail": mapped.data}
            outcome_status = (
                SendVerificationRequest.Status.DEFINITELY_FAILED if mapped.status_code < 500 else failure_status(exc)
            )
            outcome = SendOutcome(
                payload,
                mapped.status_code,
                outcome_status,
                str(getattr(exc, "challenge_id", "") or lease.record.otp_challenge_id),
            )
        except Exception:  # noqa: BLE001 - a post-claim unclassified failure is ambiguous.
            logger.exception("Protected send outcome could not be confirmed for %s", lease.record.request_id)
            outcome = SendOutcome(
                {"code": "send_unknown", "detail": "The send request outcome could not be confirmed."},
                status.HTTP_409_CONFLICT,
                SendVerificationRequest.Status.UNKNOWN,
                str(getattr(exc, "challenge_id", "") or lease.record.otp_challenge_id),
            )

    _finalize(lease.record, outcome)
    return replay_response(lease.record)


def serialize_request_status(record: SendVerificationRequest) -> dict:
    response = replay_response(record)
    is_reset = record.operation == OP_PASSWORD_RESET_REQUEST_CODE
    return {
        "request_id": str(record.request_id),
        "status": "submitted" if is_reset else record.status,
        "code": None if is_reset else response.data.get("code") or None,
        "result": response.data,
        "challenge_id": response.data.get("challenge_id") if is_reset else record.otp_challenge_id or None,
        "http_status": response.status_code,
    }
