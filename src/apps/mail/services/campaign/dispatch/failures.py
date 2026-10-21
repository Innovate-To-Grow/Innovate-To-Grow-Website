"""Classifying delivery failures into the outbox's retry / fail / review outcomes."""

from botocore.exceptions import BotoCoreError, ClientError
from django.db import OperationalError
from django.utils import timezone

from apps.core.services.aws.provider_outcomes import (
    PROVIDER_OUTCOME_PERMANENT,
    PROVIDER_OUTCOME_TRANSIENT,
    classify_aws_send_failure,
)
from apps.core.services.background_jobs import PermanentJobError, TransientJobError, UncertainJobError
from apps.mail.services.send_campaign.transport import SES_OUTCOME_PERMANENT, SES_OUTCOME_TRANSIENT


def _job_error_for_ses_result(result):
    if result.outcome == SES_OUTCOME_TRANSIENT:
        return TransientJobError(result.error or "SES temporarily rejected the request.")
    if result.outcome == SES_OUTCOME_PERMANENT:
        return PermanentJobError(result.error or "SES rejected the request.")
    return UncertainJobError(result.error or "SES request outcome could not be confirmed.")


def _exception_chain(exc):
    seen = set()
    current = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _classify_sms_job_error(exc):
    from apps.authn.services.sms import (
        PhoneVerificationInvalid,
        PhoneVerificationThrottled,
    )

    chain = tuple(_exception_chain(exc))
    if any(isinstance(item, PhoneVerificationThrottled) for item in chain):
        return TransientJobError("SMS provider temporarily throttled the request.")
    if any(isinstance(item, PhoneVerificationInvalid) for item in chain):
        return PermanentJobError("SMS provider rejected the request.")
    provider_error = next(
        (item for item in chain if isinstance(item, ClientError | BotoCoreError)),
        None,
    )
    if provider_error is not None:
        outcome, message = classify_aws_send_failure(provider_error, provider="SMS")
        if outcome == PROVIDER_OUTCOME_TRANSIENT:
            return TransientJobError(message)
        if outcome == PROVIDER_OUTCOME_PERMANENT:
            return PermanentJobError(message)
        return UncertainJobError(message)
    return UncertainJobError("SMS request outcome could not be confirmed.")


def _delivery_failure_values(exc) -> tuple[str, str, object]:
    now = timezone.now()
    if isinstance(exc, TransientJobError):
        return "retry", "Temporary delivery failure; retry scheduled.", None
    if isinstance(exc, PermanentJobError):
        return "failed", "The provider rejected this delivery.", None
    return "uncertain", "Provider call outcome is uncertain; review before retrying.", now


def _classify_pre_provider_error(exc):
    chain = tuple(_exception_chain(exc))
    if any(isinstance(item, OperationalError | TimeoutError | ConnectionError) for item in chain):
        return TransientJobError("Delivery preparation failed temporarily.")
    return PermanentJobError("Delivery failed before the provider call began.")
