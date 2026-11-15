"""Outbox handler that sends one SMS campaign recipient through AWS End User Messaging, on the bulk delivery lane
(``core.services.aws.sms_send`` paces it; a deferral reruns the job at its slot without using up an attempt).

Before anything is claimed, SMS quiet hours defer the job to their end (its attempt refunded). A number on the SMS
opt-out list, checked again before sending (and refused by AWS as opted out), is recorded as "Opted out", and a
message whose links were turned off meanwhile as failed with that reason; both end the job without a provider call.
"""

from django.utils import timezone

from apps.core.models import AWSCredentialConfig
from apps.core.services.aws.sms_errors import SmsOptedOut
from apps.core.services.aws.sms_send import resolve_sender, send_text_message
from apps.core.services.background_jobs import DeferredJobError, JobClaimLost, PermanentJobError, UncertainJobError
from apps.core.services.background_jobs.delivery import deferral_of, provider_call_guard
from apps.core.services.delivery_rates import Lane
from apps.mail.models import SmsConfig, SmsRecipientLog
from apps.mail.services.sms.compose import CampaignLinks, render_campaign_text
from apps.mail.services.sms.errors import SmsSendRefused
from apps.mail.services.sms.opt_outs import is_opted_out
from apps.mail.services.sms.quiet_hours import HELD_LOG_MESSAGE, held_until
from apps.mail.services.sms.sender import skip_opted_out_log

from .channels import SMS, aggregate_sms_campaign, mark_log_processing, release_failed_log
from .failures import _classify_pre_provider_error, _classify_sms_job_error, _delivery_failure_values

CLAIM_LOST_MESSAGE = "Background job claim was lost before SNS invocation."


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


def _defer_for_quiet_hours(log, config) -> None:
    """Inside SMS quiet hours: note it on the log and run the job again when they end (attempt refunded)."""
    until = held_until(config=config)
    if until is None:
        return
    SmsRecipientLog.objects.filter(pk=log.pk, status__in=("pending", "retry")).update(
        status="retry", error_message=HELD_LOG_MESSAGE, available_at=until, updated_at=timezone.now()
    )
    raise DeferredJobError(HELD_LOG_MESSAGE, until=until)


def _recipient(log) -> dict:
    member = log.member
    return {
        "member_id": log.member_id,
        "phone": log.phone_number,
        "first_name": getattr(member, "first_name", "") if member else "",
        "last_name": getattr(member, "last_name", "") if member else "",
        "full_name": log.recipient_name,
    }


def _end_without_sending(log, job, *, refused: SmsSendRefused | None = None) -> None:
    """The job decided not to send (opted out, or a policy refusal): record it on the log it holds and succeed, so
    the outbox never replaces that reason with a generic failure."""
    if refused is None:
        skip_opted_out_log(log, claim_token=job.claim_token)
    else:
        release_failed_log(SMS, log, job, status="failed", error_message=str(refused), uncertain_at=None)
    aggregate_sms_campaign(log.campaign_id)


def send_sms_recipient_job(job) -> None:
    log = SmsRecipientLog.objects.select_related("campaign", "campaign__event", "member").get(
        pk=job.payload["recipient_log_id"]
    )
    if log.status in SMS.terminal_statuses:
        aggregate_sms_campaign(log.campaign_id)
        return
    sms_config = SmsConfig.load()
    _defer_for_quiet_hours(log, sms_config)
    if not mark_log_processing(SMS, log, job):
        raise PermanentJobError("SMS recipient log is no longer eligible for delivery.")
    if is_opted_out(log.phone_number):
        _end_without_sending(log, job)
        return
    try:
        config = AWSCredentialConfig.load()
        if not config.sns_configured:
            raise RuntimeError("SMS delivery is not configured.")
        links = CampaignLinks(log.campaign, sms_config)
        message = render_campaign_text(log.campaign, _recipient(log), links=links, config=sms_config)
        message_id = _send_via_sms(
            config=config,
            phone_number=log.phone_number,
            message=message,
            before_provider_call=provider_call_guard(job, CLAIM_LOST_MESSAGE),
        )
        _record_sms_sent(log, job, message_id)
    except JobClaimLost:
        raise
    except SmsOptedOut:
        _end_without_sending(log, job)
        return
    except SmsSendRefused as refused:
        _end_without_sending(log, job, refused=refused)
        return
    except Exception as exc:
        classified = _classified_sms_failure(exc, job)
        log_status, error_message, uncertain_at = _delivery_failure_values(classified)
        release_failed_log(SMS, log, job, status=log_status, error_message=error_message, uncertain_at=uncertain_at)
        aggregate_sms_campaign(log.campaign_id)
        raise classified from exc
    aggregate_sms_campaign(log.campaign_id)
