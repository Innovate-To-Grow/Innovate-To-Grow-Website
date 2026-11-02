"""Outbox handler that sends one SMS campaign recipient through AWS End User Messaging, on the bulk delivery lane
(``core.services.aws.sms_send`` paces it; a deferral reruns the job at its slot without using up an attempt)."""

from django.utils import timezone

from apps.core.models import AWSCredentialConfig
from apps.core.services.aws.sms_send import resolve_sender, send_text_message
from apps.core.services.background_jobs import (
    DeferredJobError,
    JobClaimLost,
    PermanentJobError,
    UncertainJobError,
)
from apps.core.services.background_jobs.delivery import deferral_of
from apps.core.services.delivery_rates import Lane
from apps.mail.models import SmsRecipientLog
from apps.mail.services.campaign.personalize import personalize

from .channels import SMS, aggregate_sms_campaign, mark_log_processing, release_failed_log
from .failures import _classify_pre_provider_error, _classify_sms_job_error, _delivery_failure_values


def _send_via_sms(*, config, phone_number: str, message: str, before_provider_call) -> str:
    """Send once with SDK retries disabled so the outbox owns retry policy; campaigns use the bulk lane."""
    return send_text_message(
        phone_number,
        message,
        lane=Lane.BULK,
        sender=resolve_sender(config),
        before_provider_call=before_provider_call,
    )


def _classified_sms_failure(exc: Exception, job) -> Exception:
    deferred = deferral_of(exc)
    if deferred is not None:
        # Held back by the delivery-rate limiter before any provider call: run again at the slot.
        return DeferredJobError(str(deferred), until=deferred.until)
    if job.provider_call_started_at is None:
        return _classify_pre_provider_error(exc)
    return _classify_sms_job_error(exc)


def _record_sms_sent(log, job, message_id: str) -> None:
    updated = SmsRecipientLog.objects.filter(
        pk=log.pk,
        status="processing",
        claim_token=job.claim_token,
    ).update(
        status="sent",
        provider="aws_sns",
        error_message="",
        sns_message_id=message_id,
        sent_at=timezone.now(),
        claim_token=None,
        claimed_at=None,
        uncertain_at=None,
        updated_at=timezone.now(),
    )
    if not updated:
        raise UncertainJobError(
            "SNS accepted the delivery, but the recipient-log claim was lost before it could be recorded."
        )


def send_sms_recipient_job(job) -> None:
    log = SmsRecipientLog.objects.select_related("campaign", "member").get(pk=job.payload["recipient_log_id"])
    if log.status == "sent":
        aggregate_sms_campaign(log.campaign_id)
        return
    if not mark_log_processing(SMS, log, job):
        raise PermanentJobError("SMS recipient log is no longer eligible for delivery.")
    try:
        config = AWSCredentialConfig.load()
        if not config.sns_configured:
            raise RuntimeError("SMS delivery is not configured.")
        context = {
            "first_name": getattr(log.member, "first_name", "") if log.member else "",
            "last_name": getattr(log.member, "last_name", "") if log.member else "",
            "full_name": log.recipient_name,
        }
        message = personalize(log.campaign.message, context)

        def begin_provider_call():
            if not job.begin_provider_call():
                raise JobClaimLost("Background job claim was lost before SNS invocation.")

        message_id = _send_via_sms(
            config=config,
            phone_number=log.phone_number,
            message=message,
            before_provider_call=begin_provider_call,
        )
        _record_sms_sent(log, job, message_id)
    except JobClaimLost:
        raise
    except Exception as exc:
        classified = _classified_sms_failure(exc, job)
        log_status, error_message, uncertain_at = _delivery_failure_values(classified)
        release_failed_log(SMS, log, job, status=log_status, error_message=error_message, uncertain_at=uncertain_at)
        aggregate_sms_campaign(log.campaign_id)
        raise classified from exc
    aggregate_sms_campaign(log.campaign_id)
