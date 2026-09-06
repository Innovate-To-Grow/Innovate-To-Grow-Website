"""Standard email delivery failure taxonomy."""

from apps.core.services.aws.provider_outcomes import (
    PROVIDER_OUTCOME_PERMANENT,
    PROVIDER_OUTCOME_TRANSIENT,
    PROVIDER_OUTCOME_UNCERTAIN,
    ProviderDeliveryError,
)


class EmailDeliveryError(ProviderDeliveryError):
    """Base class for sanitized, classified email delivery failures."""


class TransientEmailDeliveryError(EmailDeliveryError):
    """A confirmed pre-acceptance failure that is safe to retry."""

    def __init__(self, message: str):
        super().__init__(message, outcome=PROVIDER_OUTCOME_TRANSIENT)


class PermanentEmailDeliveryError(EmailDeliveryError):
    """A failure that retrying unchanged will not resolve."""

    def __init__(self, message: str):
        super().__init__(message, outcome=PROVIDER_OUTCOME_PERMANENT)


class UncertainEmailDeliveryError(EmailDeliveryError):
    """A failure where provider acceptance cannot be determined safely."""

    def __init__(self, message: str):
        super().__init__(message, outcome=PROVIDER_OUTCOME_UNCERTAIN)
