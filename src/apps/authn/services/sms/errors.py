"""Phone verification limits, challenge states and errors, shared by sending (``sns_verify``) and ``checks``."""

from __future__ import annotations

import math

from apps.authn.models import PhoneVerificationChallenge
from apps.core.services.aws.provider_outcomes import PROVIDER_OUTCOME_TRANSIENT, PROVIDER_OUTCOME_UNCERTAIN

OTP_TTL_SECONDS = 600
VERIFIED_GRANT_TTL_SECONDS = 900
MAX_VERIFY_ATTEMPTS = 5
MAX_SENDS_PER_HOUR = 10
DEFAULT_STATUS = "pending"
DEFAULT_PURPOSE = PhoneVerificationChallenge.Purpose.PHONE_AUTH
ACTIVE_STATUSES = (
    PhoneVerificationChallenge.Status.SENDING,
    PhoneVerificationChallenge.Status.PENDING,
    PhoneVerificationChallenge.Status.VERIFIED,
)
VERIFIABLE_STATUSES = (
    PhoneVerificationChallenge.Status.SENDING,
    PhoneVerificationChallenge.Status.PENDING,
)


class PhoneVerificationError(RuntimeError):
    """Base exception for phone verification failures."""


class PhoneVerificationThrottled(PhoneVerificationError):
    """Too many verification attempts."""


class PhoneVerificationInvalid(PhoneVerificationError):
    """Invalid or expired verification code."""


class PhoneVerificationDeliveryError(PhoneVerificationError):
    """Failed to send SMS."""

    def __init__(
        self,
        message: str = "Failed to send verification SMS.",
        *,
        outcome: str = PROVIDER_OUTCOME_UNCERTAIN,
        challenge_id: str = "",
    ):
        super().__init__(message)
        self.outcome = outcome
        self.challenge_id = challenge_id


BUSY_MESSAGE = "SMS delivery is busy right now; please try again in about {seconds} seconds."


class PhoneVerificationBusy(PhoneVerificationDeliveryError):
    """SMS delivery is held back (the delivery-rate limiter, or AWS throttling): nothing was sent, so asking again
    in ``retry_after`` seconds is safe. The per-number cap stays ``PhoneVerificationThrottled``."""

    def __init__(self, retry_after: float | None = None, *, challenge_id: str = ""):
        self.retry_after = max(1, math.ceil(retry_after or 0))
        super().__init__(
            BUSY_MESSAGE.format(seconds=self.retry_after),
            outcome=PROVIDER_OUTCOME_TRANSIENT,
            challenge_id=challenge_id,
        )
