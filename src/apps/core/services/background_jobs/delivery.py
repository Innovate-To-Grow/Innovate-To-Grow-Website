"""Helpers for job handlers that call an email or SMS provider.

Domain apps own their handlers (registered with ``register_job_kind``); these are
the pieces every provider-calling handler shares. Pacing is not one of them: the
email facade and the SMS sender admit every request through the delivery-rate
limiter themselves.
"""

from apps.core.services.aws.provider_outcomes import PROVIDER_OUTCOME_PERMANENT, PROVIDER_OUTCOME_TRANSIENT
from apps.core.services.delivery_rates import RateDeferred

from .errors import exception_chain
from .worker import DeferredJobError, JobClaimLost, PermanentJobError, TransientJobError, UncertainJobError

PROVIDER_CLAIM_LOST_MESSAGE = "Background job claim was lost before the email provider call."


def deferral_of(exc: BaseException) -> RateDeferred | None:
    """The limiter's deferral behind ``exc`` (anywhere in its cause chain), or None."""
    return next((item for item in exception_chain(exc) if isinstance(item, RateDeferred)), None)


def provider_job_error(exc):
    """Map a provider's delivery outcome to the job error that drives retry and quarantine.

    A message the delivery-rate limiter held back is a ``DeferredJobError``: it runs again at its slot without using
    up an attempt.
    """
    deferred = deferral_of(exc)
    if deferred is not None:
        return DeferredJobError(str(deferred), until=deferred.until)
    if exc.outcome == PROVIDER_OUTCOME_TRANSIENT:
        return TransientJobError(str(exc), retry_after=getattr(exc, "retry_after", None))
    if exc.outcome == PROVIDER_OUTCOME_PERMANENT:
        return PermanentJobError(str(exc))
    return UncertainJobError(str(exc))


def provider_call_guard(job, message: str = PROVIDER_CLAIM_LOST_MESSAGE):
    """Return a callback that records the provider call on ``job``, or raises if the claim was lost.

    Handlers pass it to the sender as ``before_provider_call`` so a job whose claim
    expired never reaches the provider a second time.
    """

    def begin_provider_call():
        if not job.begin_provider_call():
            raise JobClaimLost(message)

    return begin_provider_call
