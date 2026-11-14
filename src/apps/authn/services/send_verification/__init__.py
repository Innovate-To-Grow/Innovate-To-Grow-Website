"""Proof-of-work protection for every endpoint that sends a code or a link (send verification).

``rules`` holds the vocabulary and settings, ``proofs`` the challenge a client solves and how its proof is checked,
and ``guard`` the protected send itself (consume, reserve, dispatch, finalize) with its HTTP wrapper. Callers import
from this package.
"""

from .guard import consume_and_reserve, extract_verification_fields, lookup_request
from .guard.cleanup import cleanup_expired_records, clear_expired_sessions
from .guard.http import guarded_send, serialize_request_status, verification_error_response
from .proofs.challenges import issue_challenge, serialize_challenge
from .rules.constants import (
    ALL_OPERATIONS,
    FIELD_CHALLENGE_ID,
    FIELD_PAYLOAD,
    FIELD_REQUEST_ID,
    OP_ADMIN_LOGIN_REMEMBERED_CODE,
    OP_ADMIN_LOGIN_REQUEST_CODE,
    OP_ADMIN_LOGIN_RESEND,
    OP_CHANGE_PASSWORD_REQUEST_CODE,
    OP_CONTACT_EMAIL_CREATE,
    OP_CONTACT_EMAIL_REQUEST_VERIFICATION,
    OP_CONTACT_PHONE_REQUEST_VERIFICATION,
    OP_DELETE_ACCOUNT_REQUEST_CODE,
    OP_EMAIL_AUTH_REQUEST_CODE,
    OP_EVENT_SEND_PHONE_CODE,
    OP_EVENT_SEND_SECONDARY_EMAIL_CODE,
    OP_LOGIN_REQUEST_CODE,
    OP_PASSWORD_RESET_REQUEST_CODE,
    OP_PHONE_AUTH_REQUEST_CODE,
    OP_REGISTER,
    OP_REGISTER_RESEND_CODE,
)
from .rules.exceptions import SendVerificationError
from .rules.hashing import fingerprint_payload

__all__ = [
    "ALL_OPERATIONS",
    "FIELD_CHALLENGE_ID",
    "FIELD_PAYLOAD",
    "FIELD_REQUEST_ID",
    "OP_ADMIN_LOGIN_REMEMBERED_CODE",
    "OP_ADMIN_LOGIN_REQUEST_CODE",
    "OP_ADMIN_LOGIN_RESEND",
    "OP_CHANGE_PASSWORD_REQUEST_CODE",
    "OP_CONTACT_EMAIL_CREATE",
    "OP_CONTACT_EMAIL_REQUEST_VERIFICATION",
    "OP_CONTACT_PHONE_REQUEST_VERIFICATION",
    "OP_DELETE_ACCOUNT_REQUEST_CODE",
    "OP_EMAIL_AUTH_REQUEST_CODE",
    "OP_EVENT_SEND_PHONE_CODE",
    "OP_EVENT_SEND_SECONDARY_EMAIL_CODE",
    "OP_LOGIN_REQUEST_CODE",
    "OP_PASSWORD_RESET_REQUEST_CODE",
    "OP_PHONE_AUTH_REQUEST_CODE",
    "OP_REGISTER",
    "OP_REGISTER_RESEND_CODE",
    "SendVerificationError",
    "cleanup_expired_records",
    "clear_expired_sessions",
    "consume_and_reserve",
    "extract_verification_fields",
    "fingerprint_payload",
    "guarded_send",
    "issue_challenge",
    "lookup_request",
    "serialize_challenge",
    "serialize_request_status",
    "verification_error_response",
]
