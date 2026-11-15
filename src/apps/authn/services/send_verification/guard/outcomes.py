"""Delivery outcomes passed from business services to the protected-send guard."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from apps.authn.models import SendVerificationRequest
from apps.core.services.aws.provider_outcomes import PROVIDER_OUTCOME_UNCERTAIN

_active_request = ContextVar("protected_send_request", default=None)


def active_send_request_id() -> str:
    record = _active_request.get()
    return str(record.request_id) if record is not None else ""


@contextmanager
def delivery_context(record):
    token = _active_request.set(record)
    try:
        yield
    finally:
        _active_request.reset(token)


def record_otp_challenge(challenge_id: str) -> None:
    """Persist the OTP reference before the external call can become ambiguous."""
    record = _active_request.get()
    if record is not None:
        SendVerificationRequest.objects.filter(pk=record.pk, status=SendVerificationRequest.Status.SENDING).update(
            otp_challenge_id=str(challenge_id),
        )
        record.otp_challenge_id = str(challenge_id)


@dataclass(frozen=True)
class SendOutcome:
    payload: dict
    http_status: int
    status: str
    otp_challenge_id: str = ""
    provider_message_id: str = ""


def failure_status(exc: Exception) -> str:
    """Unknown is the safe default for an unclassified delivery failure."""
    if getattr(exc, "outcome", PROVIDER_OUTCOME_UNCERTAIN) == PROVIDER_OUTCOME_UNCERTAIN:
        return SendVerificationRequest.Status.UNKNOWN
    return SendVerificationRequest.Status.DEFINITELY_FAILED


def public_reset_payload(challenge_id: str) -> dict:
    return {
        "message": "If an eligible account exists, check your messages for a verification code.",
        "challenge_id": challenge_id,
        "status": "submitted",
    }
