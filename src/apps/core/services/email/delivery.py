"""Provider-neutral email delivery facade.

Every message goes through the delivery-rate limiter: it is admitted on its lane (transactional by default; only
campaigns pass ``lane=Lane.BULK``), waits for its slot outside any transaction, is handed to the provider, and the
provider's answer is recorded. Admission comes before the caller's ``before_provider_call``, so an
``EmailRateDeferred`` always means "certainly not sent".
"""

import logging

from apps.core.services.aws.provider_outcomes import PROVIDER_OUTCOME_PERMANENT, PROVIDER_OUTCOME_UNCERTAIN
from apps.core.services.delivery_rates import (
    Lane,
    RateDeferred,
    RateRefused,
    admit,
    none,
    not_now,
    ok,
    record,
    release,
    uncertain,
)

from .contracts import DeliveryResult, EmailMessage
from .exceptions import (
    EmailDeliveryError,
    EmailRateDeferred,
    PermanentEmailDeliveryError,
    TransientEmailDeliveryError,
    with_signal,
)
from .registry import resolve_provider

logger = logging.getLogger(__name__)


class _Boundary:
    """Wraps the caller's ``before_provider_call`` and notes whether the provider call was reached."""

    def __init__(self, callback):
        self.callback = callback
        self.entered = False

    def __call__(self):
        if self.callback is not None:
            self.callback()
        self.entered = True


class EmailDeliveryService:
    """Deliver through one explicitly configured provider."""

    def __init__(self, config: object | None = None):
        if config is None:
            from apps.core.models import EmailServiceConfig

            config = EmailServiceConfig.load()
        self.config = config

    def send(
        self, message: EmailMessage, *, before_provider_call=None, lane: str = Lane.TRANSACTIONAL, **provider_options
    ) -> DeliveryResult:
        if not getattr(self.config, "is_active", False):
            raise PermanentEmailDeliveryError("No active email service configuration exists.")
        provider = resolve_provider(self.config, **provider_options)
        admission = _admit(provider, message, lane)
        boundary = _Boundary(before_provider_call)
        try:
            result = provider.send(message, before_provider_call=boundary)
        except EmailDeliveryError as exc:
            settled = _settle_failure(admission, exc, boundary.entered)
            if settled is exc:
                raise
            raise settled from exc
        except BaseException:
            # The caller's callback refused (a lost job claim) or the provider failed unexpectedly.
            _settle(admission, uncertain("exception") if boundary.entered else None)
            raise
        _settle(admission, ok())
        return result


def _admit(provider, message: EmailMessage, lane: str):
    try:
        return admit(provider.rate_channel, provider.rate_identity(), lane=lane, **provider.rate_costs(message))
    except RateDeferred as exc:
        raise EmailRateDeferred(exc) from None
    except RateRefused as exc:
        raise PermanentEmailDeliveryError(
            f"The email has more recipients than the provider's daily limit allows ({exc.reason})."
        ) from None


def _settle(admission, signal) -> None:
    """Record ``signal`` (None: the provider was never reached, so give the slot back). A failure to record is
    logged, never raised: the message's own outcome is already decided."""
    try:
        if signal is None:
            release(admission)
        else:
            record(admission, signal)
    except Exception:  # noqa: BLE001 - the delivery outcome must reach the caller unchanged.
        logger.exception("Could not record the delivery-rate outcome of an email")


def _settle_failure(admission, exc: EmailDeliveryError, entered: bool) -> EmailDeliveryError:
    """Record the provider's answer to a failed send; return the error to raise.

    A "not now" answer (a throttle, a pause, a used-up quota) or an account-level stop the provider reported as
    permanent becomes transient: the message was not taken, and the limiter holds the next ones back meanwhile.
    """
    signal = exc.rate_signal
    if signal is None and entered:
        signal = uncertain("unconfirmed") if exc.outcome == PROVIDER_OUTCOME_UNCERTAIN else none("rejected")
    _settle(admission, signal)
    if not not_now(signal) or exc.outcome != PROVIDER_OUTCOME_PERMANENT:
        return exc
    wait = signal.retry_after or signal.pause_seconds or signal.breaker_seconds
    return with_signal(TransientEmailDeliveryError(str(exc), retry_after=wait), signal)


def deliver_email(
    message: EmailMessage,
    *,
    config: object | None = None,
    before_provider_call=None,
    retry_config=None,
    configuration_set: str | None = None,
    lane: str = Lane.TRANSACTIONAL,
) -> DeliveryResult:
    """Deliver one message through the active or supplied configuration, on ``lane`` (``Lane.BULK`` for campaigns)."""
    return EmailDeliveryService(config).send(
        message,
        before_provider_call=before_provider_call,
        lane=lane,
        retry_config=retry_config,
        configuration_set=configuration_set,
    )
