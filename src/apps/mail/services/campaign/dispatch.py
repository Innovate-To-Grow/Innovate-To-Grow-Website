import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.db import OperationalError, transaction
from django.db.models import Count
from django.utils import timezone

from apps.core.models import AWSCredentialConfig, BackgroundJob, EmailServiceConfig
from apps.core.services.aws.credentials import resolve_aws_credentials
from apps.core.services.aws.provider_outcomes import (
    NO_PROVIDER_RETRIES,
    PROVIDER_OUTCOME_PERMANENT,
    PROVIDER_OUTCOME_TRANSIENT,
    classify_aws_send_failure,
)
from apps.core.services.background_jobs import (
    JobClaimLost,
    PermanentJobError,
    TransientJobError,
    UncertainJobError,
    configured_ses_rate,
    enqueue_job,
    jobs_enabled,
    wait_for_delivery_slot,
)
from apps.core.services.helpers.in_process import start_in_process_task
from apps.mail.models import EmailCampaign, RecipientLog, SmsCampaign, SmsRecipientLog
from apps.mail.services.audience import get_recipients
from apps.mail.services.campaign.personalize import personalize
from apps.mail.services.campaign.preview import render_email_html
from apps.mail.services.campaign.state import campaign_state
from apps.mail.services.send_campaign.runner import (
    _recipient_context,
    _unsubscribe_url_for,
)
from apps.mail.services.send_campaign.transport import (
    SES_OUTCOME_PERMANENT,
    SES_OUTCOME_TRANSIENT,
    _get_configuration_set_name,
    _get_ses_client,
    _send_via_ses,
)
from apps.mail.services.sms.audience import get_sms_recipients

logger = logging.getLogger(__name__)

_EMAIL_SUCCESS_STATUSES = {"sent", "delivered"}
_EMAIL_PROVIDER_TERMINAL_STATUSES = {
    *_EMAIL_SUCCESS_STATUSES,
    "bounced",
    "complained",
    "rejected",
}


def dispatch_email_campaign(campaign: EmailCampaign, *, sent_by):
    if not jobs_enabled():
        return _start_in_process_email_campaign(campaign, sent_by=sent_by)
    return queue_email_campaign(campaign, sent_by=sent_by)


def dispatch_sms_campaign(campaign: SmsCampaign, *, sent_by):
    if not jobs_enabled():
        return _start_in_process_sms_campaign(campaign, sent_by=sent_by)
    return queue_sms_campaign(campaign, sent_by=sent_by)


def _start_in_process_email_campaign(campaign: EmailCampaign, *, sent_by) -> dict[str, int]:
    """Preserve the legacy non-blocking send path until a worker is deployed."""

    updated = EmailCampaign.objects.filter(pk=campaign.pk, status="draft").update(
        status="sending",
        sent_by_id=sent_by.pk,
        sent_count=0,
        failed_count=0,
        error_message="",
        sent_at=None,
        updated_at=timezone.now(),
    )
    if not updated:
        raise ValueError("Campaign is no longer in draft state.")
    try:
        start_in_process_task(
            _run_in_process_email_campaign,
            campaign.pk,
            sent_by.pk,
            name=f"email-campaign-{campaign.pk}",
            daemon=False,
        )
    except Exception:
        EmailCampaign.objects.filter(pk=campaign.pk, status="sending").update(
            status="failed",
            error_message="Campaign send could not be started. Check server logs for details.",
            updated_at=timezone.now(),
        )
        raise
    return {"total": 0, "sent": 0, "failed": 0}


def _run_in_process_email_campaign(campaign_id, sent_by_id) -> None:
    from django.contrib.auth import get_user_model

    from apps.mail.services.send_campaign import send_campaign

    try:
        campaign = EmailCampaign.objects.get(pk=campaign_id)
        sent_by = get_user_model().objects.get(pk=sent_by_id)
        send_campaign(campaign, sent_by=sent_by)
    except Exception:
        logger.exception("Background send failed for email campaign %s", campaign_id)
        EmailCampaign.objects.filter(pk=campaign_id, status__in=["draft", "sending"]).update(
            status="failed",
            error_message="Campaign send failed. Check server logs for details.",
            updated_at=timezone.now(),
        )
        raise


def _start_in_process_sms_campaign(campaign: SmsCampaign, *, sent_by) -> dict[str, int]:
    updated = SmsCampaign.objects.filter(pk=campaign.pk, status="draft").update(
        status="sending",
        sent_by_id=sent_by.pk,
        sent_count=0,
        failed_count=0,
        error_message="",
        sent_at=None,
        updated_at=timezone.now(),
    )
    if not updated:
        raise ValueError("SMS campaign is no longer in draft state.")
    try:
        start_in_process_task(
            _run_in_process_sms_campaign,
            campaign.pk,
            sent_by.pk,
            name=f"sms-campaign-{campaign.pk}",
            daemon=False,
        )
    except Exception:
        SmsCampaign.objects.filter(pk=campaign.pk, status="sending").update(
            status="failed",
            error_message="SMS campaign send could not be started. Check server logs for details.",
            updated_at=timezone.now(),
        )
        raise
    return {"total": 0, "sent": 0, "failed": 0}


def _run_in_process_sms_campaign(campaign_id, sent_by_id) -> None:
    from django.contrib.auth import get_user_model

    from apps.mail.services.sms.sender import send_sms_campaign

    try:
        campaign = SmsCampaign.objects.get(pk=campaign_id)
        sent_by = get_user_model().objects.get(pk=sent_by_id)
        send_sms_campaign(campaign, sent_by=sent_by)
    except Exception:
        logger.exception("Background send failed for SMS campaign %s", campaign_id)
        SmsCampaign.objects.filter(pk=campaign_id, status__in=["draft", "sending"]).update(
            status="failed",
            error_message="SMS campaign send failed. Check server logs for details.",
            updated_at=timezone.now(),
        )
        raise


def queue_email_campaign(campaign: EmailCampaign, *, sent_by) -> dict[str, int]:
    recipients = get_recipients(campaign)
    now = timezone.now()
    with transaction.atomic():
        campaign = EmailCampaign.objects.select_for_update().get(pk=campaign.pk)
        if campaign.status != "draft":
            raise ValueError("Campaign is no longer in draft state.")
        for recipient in recipients:
            log, _created = RecipientLog.objects.update_or_create(
                campaign=campaign,
                email_address=recipient["email"],
                defaults={
                    "member_id": recipient["member_id"],
                    "recipient_name": recipient["full_name"],
                    "status": "pending",
                    "provider": "",
                    "error_message": "",
                    "attempts": 0,
                    "available_at": now,
                    "claim_token": None,
                    "claimed_at": None,
                    "uncertain_at": None,
                },
            )
            enqueue_job(
                kind="mail.email_recipient",
                dedupe_key=f"{campaign.pk}:{log.pk}",
                payload={"recipient_log_id": str(log.pk)},
                can_retry_after_claim=False,
            )
        campaign.status = "queued" if recipients else "sent"
        campaign.sent_by = sent_by
        campaign.total_recipients = len(recipients)
        campaign.sent_count = 0
        campaign.failed_count = 0
        campaign.error_message = ""
        campaign.sent_at = now if not recipients else None
        campaign.save(
            update_fields=[
                "status",
                "sent_by",
                "total_recipients",
                "sent_count",
                "failed_count",
                "error_message",
                "sent_at",
                "updated_at",
            ]
        )
    return {"total": len(recipients), "sent": 0, "failed": 0}


def queue_sms_campaign(campaign: SmsCampaign, *, sent_by) -> dict[str, int]:
    recipients = get_sms_recipients(campaign)
    now = timezone.now()
    with transaction.atomic():
        campaign = SmsCampaign.objects.select_for_update().get(pk=campaign.pk)
        if campaign.status != "draft":
            raise ValueError("SMS campaign is no longer in draft state.")
        for recipient in recipients:
            log, _created = SmsRecipientLog.objects.update_or_create(
                campaign=campaign,
                phone_number=recipient["phone"],
                defaults={
                    "member_id": recipient["member_id"],
                    "recipient_name": recipient["full_name"],
                    "status": "pending",
                    "provider": "aws_sns",
                    "error_message": "",
                    "attempts": 0,
                    "available_at": now,
                    "claim_token": None,
                    "claimed_at": None,
                    "uncertain_at": None,
                },
            )
            enqueue_job(
                kind="mail.sms_recipient",
                dedupe_key=f"{campaign.pk}:{log.pk}",
                payload={"recipient_log_id": str(log.pk)},
                can_retry_after_claim=False,
            )
        campaign.status = "queued" if recipients else "sent"
        campaign.sent_by = sent_by
        campaign.total_recipients = len(recipients)
        campaign.sent_count = 0
        campaign.failed_count = 0
        campaign.error_message = ""
        campaign.sent_at = now if not recipients else None
        campaign.save(
            update_fields=[
                "status",
                "sent_by",
                "total_recipients",
                "sent_count",
                "failed_count",
                "error_message",
                "sent_at",
                "updated_at",
            ]
        )
    return {"total": len(recipients), "sent": 0, "failed": 0}


def _mark_email_processing(log: RecipientLog, job) -> bool:
    with transaction.atomic():
        owns_claim = (
            BackgroundJob.objects.select_for_update()
            .filter(
                pk=job.pk,
                status=BackgroundJob.Status.PROCESSING,
                claim_token=job.claim_token,
            )
            .exists()
        )
        if not owns_claim:
            return False
        return bool(
            RecipientLog.objects.filter(
                pk=log.pk,
                status__in=["pending", "retry", "processing"],
            ).update(
                status="processing",
                attempts=job.attempts,
                available_at=job.available_at,
                claim_token=job.claim_token,
                claimed_at=job.claimed_at,
                error_message="",
                updated_at=timezone.now(),
            )
        )


def _mark_sms_processing(log: SmsRecipientLog, job) -> bool:
    with transaction.atomic():
        owns_claim = (
            BackgroundJob.objects.select_for_update()
            .filter(
                pk=job.pk,
                status=BackgroundJob.Status.PROCESSING,
                claim_token=job.claim_token,
            )
            .exists()
        )
        if not owns_claim:
            return False
        return bool(
            SmsRecipientLog.objects.filter(
                pk=log.pk,
                status__in=["pending", "retry", "processing"],
            ).update(
                status="processing",
                attempts=job.attempts,
                available_at=job.available_at,
                claim_token=job.claim_token,
                claimed_at=job.claimed_at,
                error_message="",
                updated_at=timezone.now(),
            )
        )


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


def _send_via_sms(*, config, phone_number: str, message: str, before_provider_call) -> str:
    """Send once with SDK retries disabled so the outbox owns retry policy."""
    origination_identity = config.resolved_sms_from_number()
    if not origination_identity:
        raise ValueError("SMS origination identity is not configured.")
    credentials = resolve_aws_credentials("sns")
    client = boto3.client(
        "pinpoint-sms-voice-v2",
        region_name=credentials.region,
        aws_access_key_id=credentials.access_key_id,
        aws_secret_access_key=credentials.secret_access_key,
        config=NO_PROVIDER_RETRIES,
    )
    before_provider_call()
    response = client.send_text_message(
        DestinationPhoneNumber=phone_number,
        OriginationIdentity=origination_identity,
        MessageBody=message,
        MessageType="TRANSACTIONAL",
    )
    return response.get("MessageId", "")


def send_email_recipient_job(job) -> None:
    log = RecipientLog.objects.select_related("campaign", "member").get(pk=job.payload["recipient_log_id"])
    if log.status in _EMAIL_PROVIDER_TERMINAL_STATUSES:
        aggregate_email_campaign(log.campaign_id)
        if log.status not in _EMAIL_SUCCESS_STATUSES:
            raise PermanentJobError("Recipient already has a terminal provider failure.")
        return
    if not _mark_email_processing(log, job):
        raise PermanentJobError("Recipient log is no longer eligible for delivery.")
    try:
        config = EmailServiceConfig.load()
        ses_client = _get_ses_client(config)
        if ses_client is None:
            raise RuntimeError("Email delivery is not configured.")
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
        wrapped_html = render_email_html(body_html, unsubscribe_url=unsubscribe_url)
        wait_for_delivery_slot("ses", configured_ses_rate(config))
        if not job.begin_provider_call():
            raise JobClaimLost("Background job claim was lost before SES invocation.")
        result = _send_via_ses(
            ses_client=ses_client,
            source=config.source_address,
            recipient=log.email_address,
            subject=subject,
            html_body=wrapped_html,
            unsubscribe_url=unsubscribe_url,
            configuration_set=_get_configuration_set_name(config),
        )
        if result.error:
            raise _job_error_for_ses_result(result)
        updated = RecipientLog.objects.filter(
            pk=log.pk,
            status="processing",
            claim_token=job.claim_token,
        ).update(
            status="sent",
            provider=result.provider,
            error_message="",
            sent_at=timezone.now(),
            ses_message_id=result.message_id,
            claim_token=None,
            claimed_at=None,
            uncertain_at=None,
            updated_at=timezone.now(),
        )
        if not updated:
            raise UncertainJobError(
                "SES accepted the delivery, but the recipient-log claim was lost before it could be recorded."
            )
    except JobClaimLost:
        raise
    except Exception as exc:
        classified = (
            exc
            if isinstance(exc, TransientJobError | PermanentJobError | UncertainJobError)
            else (
                _classify_pre_provider_error(exc)
                if job.provider_call_started_at is None
                else UncertainJobError("SES request outcome could not be confirmed.")
            )
        )
        log_status, error_message, uncertain_at = _delivery_failure_values(classified)
        RecipientLog.objects.filter(
            pk=log.pk,
            status="processing",
            claim_token=job.claim_token,
        ).update(
            status=log_status,
            error_message=error_message,
            uncertain_at=uncertain_at,
            claim_token=None,
            claimed_at=None,
            updated_at=timezone.now(),
        )
        aggregate_email_campaign(log.campaign_id)
        if classified is exc:
            raise
        raise classified from exc
    aggregate_email_campaign(log.campaign_id)


def send_sms_recipient_job(job) -> None:
    log = SmsRecipientLog.objects.select_related("campaign", "member").get(pk=job.payload["recipient_log_id"])
    if log.status == "sent":
        aggregate_sms_campaign(log.campaign_id)
        return
    if not _mark_sms_processing(log, job):
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
    except JobClaimLost:
        raise
    except Exception as exc:
        classified = (
            _classify_pre_provider_error(exc) if job.provider_call_started_at is None else _classify_sms_job_error(exc)
        )
        log_status, error_message, uncertain_at = _delivery_failure_values(classified)
        SmsRecipientLog.objects.filter(
            pk=log.pk,
            status="processing",
            claim_token=job.claim_token,
        ).update(
            status=log_status,
            error_message=error_message,
            uncertain_at=uncertain_at,
            claim_token=None,
            claimed_at=None,
            updated_at=timezone.now(),
        )
        aggregate_sms_campaign(log.campaign_id)
        raise classified from exc
    aggregate_sms_campaign(log.campaign_id)


def aggregate_email_campaign(campaign_id) -> None:
    with transaction.atomic():
        campaign = EmailCampaign.objects.select_for_update().filter(pk=campaign_id).first()
        if campaign is None:
            return
        statuses = {
            row["status"]: row["count"]
            for row in RecipientLog.objects.filter(campaign_id=campaign_id).values("status").annotate(count=Count("id"))
        }
        total = sum(statuses.values())
        sent = sum(statuses.get(status, 0) for status in ("sent", "delivered"))
        failed = sum(statuses.get(status, 0) for status in ("failed", "bounced", "complained", "rejected", "uncertain"))
        active = sum(statuses.get(status, 0) for status in ("pending", "processing", "retry"))
        state = campaign_state(total=total, sent=sent, failed=failed, active=active)
        campaign.status = state
        campaign.total_recipients = total
        campaign.sent_count = sent
        campaign.failed_count = failed
        if campaign.sent_at is None and not active:
            campaign.sent_at = timezone.now()
        campaign.error_message = "One or more deliveries need review." if failed else ""
        campaign.save(
            update_fields=[
                "status",
                "total_recipients",
                "sent_count",
                "failed_count",
                "sent_at",
                "error_message",
                "updated_at",
            ]
        )


def aggregate_sms_campaign(campaign_id) -> None:
    with transaction.atomic():
        campaign = SmsCampaign.objects.select_for_update().filter(pk=campaign_id).first()
        if campaign is None:
            return
        statuses = {
            row["status"]: row["count"]
            for row in SmsRecipientLog.objects.filter(campaign_id=campaign_id)
            .values("status")
            .annotate(count=Count("id"))
        }
        total = sum(statuses.values())
        sent = statuses.get("sent", 0)
        failed = statuses.get("failed", 0) + statuses.get("uncertain", 0)
        active = sum(statuses.get(status, 0) for status in ("pending", "processing", "retry"))
        state = campaign_state(total=total, sent=sent, failed=failed, active=active)
        campaign.status = state
        campaign.total_recipients = total
        campaign.sent_count = sent
        campaign.failed_count = failed
        if campaign.sent_at is None and not active:
            campaign.sent_at = timezone.now()
        campaign.error_message = "One or more deliveries need review." if failed else ""
        campaign.save(
            update_fields=[
                "status",
                "total_recipients",
                "sent_count",
                "failed_count",
                "sent_at",
                "error_message",
                "updated_at",
            ]
        )


def prepare_delivery_log_retry(job) -> None:
    """Mirror an explicit BackgroundJob retry into its recipient log."""
    sync_delivery_job_state(job)


def resolve_stale_delivery_job(job) -> str | None:
    """Prove completion from the recipient log after a worker crash."""

    log_id = job.payload.get("recipient_log_id")
    if not log_id:
        return None
    if job.kind == "mail.email_recipient":
        status = RecipientLog.objects.select_for_update().filter(pk=log_id).values_list("status", flat=True).first()
        if status in {"sent", "delivered"}:
            return BackgroundJob.Status.SUCCEEDED
    elif job.kind == "mail.sms_recipient":
        status = SmsRecipientLog.objects.select_for_update().filter(pk=log_id).values_list("status", flat=True).first()
        if status == "sent":
            return BackgroundJob.Status.SUCCEEDED
    else:
        return None
    if status == "uncertain":
        return BackgroundJob.Status.UNCERTAIN
    if status == "retry":
        return BackgroundJob.Status.RETRY
    if status in {"failed", "bounced", "complained", "rejected"}:
        return BackgroundJob.Status.FAILED
    return None


def sync_delivery_job_state(job) -> None:
    """Mirror retry/terminal outbox state into its recipient and campaign."""

    log_id = job.payload.get("recipient_log_id")
    if not log_id:
        return
    now = timezone.now()
    state_map = {
        BackgroundJob.Status.RETRY: (
            "retry",
            "Temporary delivery failure; retry scheduled.",
        ),
        BackgroundJob.Status.FAILED: (
            "failed",
            "Delivery failed before the provider confirmed acceptance.",
        ),
        BackgroundJob.Status.UNCERTAIN: (
            "uncertain",
            "Provider call outcome is uncertain; review before retrying.",
        ),
    }
    succeeded = job.status == BackgroundJob.Status.SUCCEEDED
    mapped = state_map.get(job.status)
    if mapped is None and not succeeded:
        return
    with transaction.atomic():
        current_job = BackgroundJob.objects.select_for_update().filter(pk=job.pk).first()
        if current_job is None or current_job.status != job.status or current_job.claim_token != job.claim_token:
            # ``job`` is an out-of-date retry/recovery snapshot. A newer worker
            # owns the row, so this mirror must not clear its recipient-log claim.
            return
        if job.kind == "mail.email_recipient":
            log = RecipientLog.objects.filter(pk=log_id).first()
            if log is None:
                return
            if succeeded:
                aggregate_email_campaign(log.campaign_id)
                return
            status, error = mapped
            update_values = {
                "status": status,
                "available_at": job.available_at,
                "claim_token": None,
                "claimed_at": None,
                "uncertain_at": now if status == "uncertain" else None,
                "error_message": error,
                "updated_at": now,
            }
            RecipientLog.objects.filter(pk=log.pk).exclude(status__in=_EMAIL_PROVIDER_TERMINAL_STATUSES).update(
                **update_values
            )
            aggregate_email_campaign(log.campaign_id)
        elif job.kind == "mail.sms_recipient":
            log = SmsRecipientLog.objects.filter(pk=log_id).first()
            if log is None:
                return
            if succeeded:
                aggregate_sms_campaign(log.campaign_id)
                return
            status, error = mapped
            update_values = {
                "status": status,
                "available_at": job.available_at,
                "claim_token": None,
                "claimed_at": None,
                "uncertain_at": now if status == "uncertain" else None,
                "error_message": error,
                "updated_at": now,
            }
            SmsRecipientLog.objects.filter(pk=log.pk).exclude(status="sent").update(**update_values)
            aggregate_sms_campaign(log.campaign_id)
