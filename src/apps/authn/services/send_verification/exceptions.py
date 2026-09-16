from __future__ import annotations

from .constants import (
    CODE_CONFLICTING_REQUEST,
    CODE_CONSUMED,
    CODE_CONTEXT_MISMATCH,
    CODE_EXPIRED,
    CODE_INVALID,
    CODE_PAUSED,
    CODE_RATE_LIMITED,
    CODE_REQUIRED,
    CODE_SEND_THROTTLED,
    CODE_SEND_UNKNOWN,
    CODE_UNAVAILABLE,
)


class SendVerificationError(Exception):
    code = CODE_UNAVAILABLE
    http_status = 503
    retry_after: int | None = None
    detail = "Send verification is temporarily unavailable."

    def __init__(self, detail: str | None = None, *, retry_after: int | None = None):
        super().__init__(detail or self.detail)
        if detail:
            self.detail = detail
        if retry_after is not None:
            self.retry_after = retry_after


class SendVerificationRequired(SendVerificationError):
    code = CODE_REQUIRED
    http_status = 400
    detail = "Verification is required before a code can be sent."


class SendVerificationInvalid(SendVerificationError):
    code = CODE_INVALID
    http_status = 400
    detail = "Verification is invalid."


class SendVerificationExpired(SendVerificationError):
    code = CODE_EXPIRED
    http_status = 400
    detail = "Verification has expired. Request a new challenge."


class SendVerificationConsumed(SendVerificationError):
    code = CODE_CONSUMED
    http_status = 400
    detail = "Verification has already been used. Request a new challenge."


class SendVerificationContextMismatch(SendVerificationError):
    code = CODE_CONTEXT_MISMATCH
    http_status = 400
    detail = "Verification does not match this request."


class SendVerificationRateLimited(SendVerificationError):
    code = CODE_RATE_LIMITED
    http_status = 429
    detail = "Too many verification attempts. Please try again later."
    retry_after = 60


class SendVerificationUnavailable(SendVerificationError):
    code = CODE_UNAVAILABLE
    http_status = 503
    detail = "Send verification is temporarily unavailable."


class SendPaused(SendVerificationError):
    code = CODE_PAUSED
    http_status = 503
    detail = "Verification-code sending is temporarily paused."


class SendThrottled(SendVerificationError):
    code = CODE_SEND_THROTTLED
    http_status = 429
    detail = "Too many verification codes requested. Please try again later."


class SendUnknown(SendVerificationError):
    code = CODE_SEND_UNKNOWN
    http_status = 409
    detail = "The previous send request is still unresolved. Do not retry a new send."


class SendRequestConflict(SendVerificationError):
    code = CODE_CONFLICTING_REQUEST
    http_status = 409
    detail = "This send request id was already used with different contents."
