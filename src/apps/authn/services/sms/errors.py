"""Phone verification limits, challenge states and errors, shared by sending (``sns_verify``) and ``checks``."""

from __future__ import annotations

from apps.authn.models import PhoneVerificationChallenge
from apps.core.services.aws.provider_outcomes import PROVIDER_OUTCOME_UNCERTAIN

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
