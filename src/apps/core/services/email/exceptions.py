"""Standard email delivery failure taxonomy."""

from apps.core.services.aws.provider_outcomes import (
    PROVIDER_OUTCOME_PERMANENT,
    PROVIDER_OUTCOME_TRANSIENT,
    PROVIDER_OUTCOME_UNCERTAIN,
    ProviderDeliveryError,
)
from apps.core.services.delivery_rates import RateDeferred


class EmailDeliveryError(ProviderDeliveryError):
    """Base class for sanitized, classified email delivery failures."""

    # What the provider's answer means for the delivery rate (a ``delivery_rates.RateSignal``), set by the provider
    # that raised it; None when no provider answer is behind the error.
    rate_signal = None


def with_signal(error: EmailDeliveryError, signal) -> EmailDeliveryError:
    """Attach the provider answer's rate signal to ``error`` and return it."""
    error.rate_signal = signal
    return error


class TransientEmailDeliveryError(EmailDeliveryError):
    """A confirmed pre-acceptance failure that is safe to retry."""

    def __init__(self, message: str, *, retry_after: float | None = None):
        super().__init__(message, outcome=PROVIDER_OUTCOME_TRANSIENT, retry_after=retry_after)


class EmailRateDeferred(RateDeferred, TransientEmailDeliveryError):
    """The delivery-rate limiter held the message back before any provider call: certainly not sent.

    It carries the limiter's ``until``, ``reason`` and ``retry_after`` (whole seconds); a background job becomes a
    ``DeferredJobError`` and runs again at ``until``.
    """

    def __init__(self, deferred: RateDeferred):
        TransientEmailDeliveryError.__init__(
            self,
            f"Email delivery is busy right now; try again in about {deferred.retry_after} seconds.",
            retry_after=deferred.retry_after,
        )
        self.until, self.reason, self.resume_at = deferred.until, deferred.reason, deferred.resume_at


class PermanentEmailDeliveryError(EmailDeliveryError):
    """A failure that retrying unchanged will not resolve."""

    def __init__(self, message: str):
        super().__init__(message, outcome=PROVIDER_OUTCOME_PERMANENT)


class UncertainEmailDeliveryError(EmailDeliveryError):
    """A failure where provider acceptance cannot be determined safely."""

    def __init__(self, message: str):
        super().__init__(message, outcome=PROVIDER_OUTCOME_UNCERTAIN)
