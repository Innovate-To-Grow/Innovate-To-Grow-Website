"""The errors of the SMS send (``sms_send``): a sanitized, classified failure, the limiter's deferral, and the
refusal of a destination that opted out."""

from apps.core.services.delivery_rates import RateDeferred, not_now

from .provider_outcomes import PROVIDER_OUTCOME_PERMANENT, PROVIDER_OUTCOME_TRANSIENT, ProviderDeliveryError

OPTED_OUT_MESSAGE = "This phone number has opted out of text messages from us."


class SmsDeliveryError(ProviderDeliveryError):
    """A sanitized SMS send failure: ``outcome`` says whether a retry is safe, ``code`` is AWS's error code and
    ``rate_signal`` what the answer meant for the delivery rate (None when AWS gave none)."""

    def __init__(self, message: str, *, outcome: str, retry_after: float | None = None, code: str = "", signal=None):
        super().__init__(message, outcome=outcome, retry_after=retry_after)
        self.code = code
        self.rate_signal = signal

    @property
    def held_back(self) -> bool:
        """AWS did not take the message but may later (``delivery_rates.not_now``): try again in ``retry_after``."""
        return not_now(self.rate_signal)


class SmsRateDeferred(RateDeferred, SmsDeliveryError):
    """The delivery-rate limiter held the SMS back before any provider call: certainly not sent. It carries the
    limiter's ``until``, ``reason``, ``resume_at`` and ``retry_after`` (whole seconds)."""

    def __init__(self, deferred: RateDeferred):
        SmsDeliveryError.__init__(
            self,
            f"SMS delivery is busy right now; try again in about {deferred.retry_after} seconds.",
            outcome=PROVIDER_OUTCOME_TRANSIENT,
            retry_after=deferred.retry_after,
        )
        self.until, self.reason, self.resume_at = deferred.until, deferred.reason, deferred.resume_at


class SmsOptedOut(SmsDeliveryError):
    """The destination opted out of the site's texts (it replied STOP, or staff opted it out): nothing was sent, and
    nothing will be until it opts back in. ``refused_by_provider`` is True when AWS itself refused it."""

    def __init__(self, *, code: str = "", signal=None, refused_by_provider: bool = False):
        super().__init__(OPTED_OUT_MESSAGE, outcome=PROVIDER_OUTCOME_PERMANENT, code=code, signal=signal)
        self.refused_by_provider = refused_by_provider
