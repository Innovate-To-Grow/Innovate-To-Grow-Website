from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from .config import SendVerificationSettings, require_ready
from .constants import ALL_OPERATIONS, KIND_EMAIL, KIND_PHONE, SMS_OPERATIONS
from .exceptions import (
    SendVerificationConsumed,
    SendVerificationContextMismatch,
    SendVerificationExpired,
    SendVerificationInvalid,
)
from .hashing import fingerprint_payload
from .metrics import emit
from .principal import principal_from_request, principals_match


def _validate_issue_input(operation: str, destination_kind: str, destination_normalized) -> None:
    if operation not in ALL_OPERATIONS:
        raise SendVerificationInvalid("Unknown verification operation.")
    if (
        destination_kind not in {KIND_EMAIL, KIND_PHONE}
        or not isinstance(destination_normalized, str)
        or not destination_normalized
        or len(destination_normalized) > 254
    ):
        raise SendVerificationInvalid("Invalid verification destination.")


def issue_challenge(
    request,
    *,
    operation: str,
    destination_kind: str,
    destination_normalized: str,
    context: dict | None = None,
):
    from altcha import create_challenge

    from apps.authn.models import SendVerificationChallenge

    _validate_issue_input(operation, destination_kind, destination_normalized)
    # No per-IP limit on issuance (campus users share one IP); sending stays capped per destination.
    config = require_ready(for_sms=destination_kind == KIND_PHONE or operation in SMS_OPERATIONS)
    principal_type, principal_key = principal_from_request(request, operation=operation)
    now = timezone.now()
    expires_at = now + timedelta(seconds=config.ttl_seconds)
    context_fingerprint = fingerprint_payload(
        {
            "operation": operation,
            "destination_kind": destination_kind,
            "destination": destination_normalized,
            **(context or {}),
        }
    )
    row = SendVerificationChallenge.objects.create(
        operation=operation,
        destination_kind=destination_kind,
        destination_normalized=destination_normalized,
        principal_type=principal_type,
        principal_key=principal_key,
        algorithm=config.algorithm,
        cost=config.cost,
        expires_at=expires_at,
        context_fingerprint=context_fingerprint,
    )
    challenge = create_challenge(
        algorithm=config.algorithm,
        cost=config.cost,
        expires_at=expires_at,
        hmac_secret=config.hmac_secret,
        hmac_key_secret=config.hmac_key_secret or None,
        data={"challenge_id": str(row.id), "operation": operation},
    )
    emit("challenge_issued", operation=operation, challenge_id=str(row.id), destination=destination_normalized)
    return row, config, challenge.to_dict()


def serialize_challenge(row, config: SendVerificationSettings, challenge_dict: dict) -> dict:
    return {
        "challenge_id": str(row.id),
        "expires_at": row.expires_at.isoformat(),
        "algorithm": config.algorithm,
        "cost": config.cost,
        "challenge": challenge_dict,
    }


def check_challenge_usable(
    challenge,
    *,
    now,
    operation: str,
    destination_kind: str,
    destination_normalized: str,
    principal_type: str,
    principal_key: str,
    channel: str = "",
) -> None:
    """A locked challenge may be spent only while pending, unexpired, and issued for this exact send."""
    from apps.authn.models import SendVerificationChallenge

    if challenge.status == SendVerificationChallenge.Status.CONSUMED:
        raise SendVerificationConsumed()
    if challenge.status != SendVerificationChallenge.Status.PENDING or challenge.expires_at <= now:
        raise SendVerificationExpired()
    if challenge.operation != operation:
        raise SendVerificationContextMismatch()
    if challenge.destination_kind != destination_kind or challenge.destination_normalized != destination_normalized:
        raise SendVerificationContextMismatch()
    if not principals_match(challenge.principal_type, challenge.principal_key, principal_type, principal_key):
        raise SendVerificationContextMismatch()
