"""Helpers for job handlers that call an email or SMS provider.

Domain apps own their handlers (registered with ``register_job_kind``); these are
the pieces every provider-calling handler shares.
"""

from apps.core.services.aws.provider_outcomes import PROVIDER_OUTCOME_PERMANENT, PROVIDER_OUTCOME_TRANSIENT

from .worker import JobClaimLost, PermanentJobError, TransientJobError, UncertainJobError

PROVIDER_CLAIM_LOST_MESSAGE = "Background job claim was lost before SES invocation."


def wait_for_email_slot() -> None:
    """Block until the active email provider's global send rate allows one more message."""
    from apps.core.models import EmailServiceConfig

    from .rate_limit import configured_ses_rate, wait_for_delivery_slot

    config = EmailServiceConfig.load()
    wait_for_delivery_slot(config.provider, configured_ses_rate(config))


def provider_job_error(exc):
    """Map a provider's delivery outcome to the job error that drives retry and quarantine."""
    if exc.outcome == PROVIDER_OUTCOME_TRANSIENT:
        return TransientJobError(str(exc))
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
