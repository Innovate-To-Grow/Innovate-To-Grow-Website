"""Outbox handler that sends one email campaign recipient through SES."""

from django.db import transaction
from django.utils import timezone

from apps.core.models import EmailServiceConfig
from apps.core.services.background_jobs import (
    JobClaimLost,
    PermanentJobError,
    TransientJobError,
    UncertainJobError,
    configured_ses_rate,
    wait_for_delivery_slot,
)
from apps.mail.models import RecipientLog
from apps.mail.services.campaign.personalize import personalize
from apps.mail.services.campaign.preview import render_email_html
from apps.mail.services.send_campaign.runner import _recipient_context, _unsubscribe_url_for
from apps.mail.services.send_campaign.transport import _get_configuration_set_name, _get_ses_client, _send_via_ses

from .channels import (
    EMAIL,
    EMAIL_PROVIDER_TERMINAL_STATUSES,
    EMAIL_SUCCESS_STATUSES,
    aggregate_email_campaign,
    mark_log_processing,
    release_failed_log,
)
from .failures import _classify_pre_provider_error, _delivery_failure_values, _job_error_for_ses_result


def _render_recipient_email(log):
    """The personalized subject, the wrapped HTML body, and the unsubscribe URL for one recipient."""
    recipient = {
        "member_id": log.member_id,
        "email": log.email_address,
        "first_name": getattr(log.member, "first_name", "") if log.member else "",
        "last_name": getattr(log.member, "last_name", "") if log.member else "",
        "full_name": log.recipient_name,
    }
    context = _recipient_context(recipient, log.campaign)
    subject = personalize(log.campaign.subject, context)
    body_html = personalize(log.campaign.body, context)
    unsubscribe_url = _unsubscribe_url_for(log.campaign, recipient)
    return subject, render_email_html(body_html, unsubscribe_url=unsubscribe_url), unsubscribe_url


def _classified_email_failure(exc: Exception, job) -> Exception:
    if isinstance(exc, TransientJobError | PermanentJobError | UncertainJobError):
        return exc
    if job.provider_call_started_at is None:
        return _classify_pre_provider_error(exc)
    return UncertainJobError("Email provider request outcome could not be confirmed.")


def send_email_recipient_job(job) -> None:
    log = RecipientLog.objects.select_related("campaign", "member").get(pk=job.payload["recipient_log_id"])
    if log.status in EMAIL_PROVIDER_TERMINAL_STATUSES:
        aggregate_email_campaign(log.campaign_id)
        if log.status not in EMAIL_SUCCESS_STATUSES:
            raise PermanentJobError("Recipient already has a terminal provider failure.")
        return
    if not mark_log_processing(EMAIL, log, job):
        raise PermanentJobError("Recipient log is no longer eligible for delivery.")
    try:
        config = EmailServiceConfig.load()
        provider_config = _get_ses_client(config)
        if provider_config is None:
            raise RuntimeError("Email delivery is not configured.")
        subject, wrapped_html, unsubscribe_url = _render_recipient_email(log)
        wait_for_delivery_slot(config.provider, configured_ses_rate(config))

        def begin_provider_call():
            if not job.begin_provider_call():
                raise JobClaimLost("Background job claim was lost before email provider invocation.")

        result = _send_via_ses(
            ses_client=provider_config,
            source=config.source_address,
            recipient=log.email_address,
            subject=subject,
            html_body=wrapped_html,
            unsubscribe_url=unsubscribe_url,
            configuration_set=_get_configuration_set_name(config),
            before_provider_call=begin_provider_call,
            recipient_log_id=log.pk,
            delivery_attempt=job.attempts,
        )
        _record_email_job_result(log, job, result)
    except JobClaimLost:
        raise
    except Exception as exc:
        classified = _classified_email_failure(exc, job)
        log_status, error_message, uncertain_at = _delivery_failure_values(classified)
        release_failed_log(EMAIL, log, job, status=log_status, error_message=error_message, uncertain_at=uncertain_at)
        aggregate_email_campaign(log.campaign_id)
        if classified is exc:
            raise
        raise classified from exc
    aggregate_email_campaign(log.campaign_id)


def _record_email_job_result(log, job, result):
    error = None
    with transaction.atomic():
        current = RecipientLog.objects.select_for_update().get(pk=log.pk)
        confirmed_by_event = (
            current.attempts == job.attempts
            and current.provider == "ses"
            and current.provider_message_id
            and current.last_sns_message_id
            and current.status in EMAIL_PROVIDER_TERMINAL_STATUSES
        )
        if confirmed_by_event:
            # A callback can arrive before the provider returns, including when
            # the response subsequently times out. Its confirmed outcome wins.
            RecipientLog.objects.filter(pk=log.pk, claim_token=job.claim_token).update(
                claim_token=None,
                claimed_at=None,
                uncertain_at=None,
                updated_at=timezone.now(),
            )
            if current.status not in EMAIL_SUCCESS_STATUSES:
                error = PermanentJobError("Recipient already has a terminal provider failure.")
        elif result.error:
            error = _job_error_for_ses_result(result)
        elif current.status == "processing" and current.claim_token == job.claim_token:
            RecipientLog.objects.filter(pk=log.pk).update(
                status="sent",
                provider=result.provider,
                error_message="",
                sent_at=timezone.now(),
                provider_message_id=result.message_id,
                claim_token=None,
                claimed_at=None,
                uncertain_at=None,
                updated_at=timezone.now(),
            )
        else:
            error = UncertainJobError(
                "The email provider accepted delivery, but the recipient-log claim was lost before it could be recorded."
            )
    if error is not None:
        raise error
