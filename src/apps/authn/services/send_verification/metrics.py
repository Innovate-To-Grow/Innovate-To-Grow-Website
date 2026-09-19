from __future__ import annotations

import logging
import unicodedata
from uuid import UUID

from . import constants
from .hashing import short_destination_hash

logger = logging.getLogger("apps.authn.send_verification")

_EVENTS = (
    "challenge_issued",
    "challenge_consumed",
    "observe_missing_proof",
    "quota_cooldown",
    "quota_destination_hourly",
    "quota_sms_daily",
    "request_replay",
    "send_finalized",
    "send_rejected",
    "cleanup",
)
_STATUSES = ("pending", "sending", "provider_accepted", "definitely_failed", "unknown")
_CODES = (
    constants.CODE_REQUIRED,
    constants.CODE_INVALID,
    constants.CODE_EXPIRED,
    constants.CODE_CONSUMED,
    constants.CODE_CONTEXT_MISMATCH,
    constants.CODE_RATE_LIMITED,
    constants.CODE_UNAVAILABLE,
    constants.CODE_SEND_UNKNOWN,
    constants.CODE_SEND_THROTTLED,
    constants.CODE_CONFLICTING_REQUEST,
    constants.CODE_PAUSED,
)


def _known_label(value: object, choices) -> str:
    # Return the trusted label itself, never the supplied object or its repr.
    return next((choice for choice in choices if choice == value), "unknown")


def _opaque_id(value: object) -> str | None:
    if isinstance(value, UUID):
        return str(value)
    if not isinstance(value, str):
        return None
    try:
        return str(UUID(value))
    except ValueError:
        return None


def _log_token(value: object) -> str:
    """Keep untrusted values within one token of one physical log record."""
    text = str(value).replace("\\", "\\\\").replace("\r", "\\r").replace("\n", "\\n")
    return "".join(
        f"\\u{ord(char):04x}" if char.isspace() or unicodedata.category(char).startswith("C") or char == "=" else char
        for char in text
    )


def emit(
    event: str,
    *,
    destination=None,
    operation=None,
    challenge_id=None,
    request_id=None,
    status=None,
    http_status=None,
    code=None,
    channel=None,
    expired_challenges=None,
    deleted_challenges=None,
    deleted_requests=None,
    **_ignored,
) -> None:
    """Log only known telemetry labels, opaque identifiers, and numeric counts."""
    fields = {}
    for key, value, choices in (
        ("operation", operation, constants.ALL_OPERATIONS),
        ("status", status, _STATUSES),
        ("code", code, _CODES),
        ("channel", channel, (constants.EMAIL_CHANNEL, constants.SMS_CHANNEL)),
    ):
        if value is not None:
            fields[key] = _known_label(value, choices)
    for key, value in (("challenge_id", challenge_id), ("request_id", request_id)):
        if (identifier := _opaque_id(value)) is not None:
            fields[key] = identifier
    for key, value in (
        ("http_status", http_status),
        ("expired_challenges", expired_challenges),
        ("deleted_challenges", deleted_challenges),
        ("deleted_requests", deleted_requests),
    ):
        if type(value) is int and value >= 0:
            fields[key] = value
    if isinstance(destination, str) and destination:
        fields["destination_hash"] = short_destination_hash(destination)
    payload = " ".join(
        f"{_log_token(key)}={_log_token(value)}" for key, value in sorted(fields.items()) if value is not None
    )
    logger.info("send_verification.%s %s", _log_token(_known_label(event, _EVENTS)), payload)
