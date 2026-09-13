import json
import logging
from typing import Any
from uuid import UUID

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.models import BackgroundJob
from apps.mail.models import RecipientLog

from .handlers import EVENT_HANDLERS, unknown

logger = logging.getLogger(__name__)


def handle_notification(envelope: dict[str, Any]) -> None:
    import apps.mail.services.ses_events as ses_api

    sns_message_id = envelope.get("MessageId", "")
    try:
        ses_event = json.loads(envelope.get("Message", ""))
    except json.JSONDecodeError as exc:
        raise ses_api.SesEventError("SNS Message is not JSON") from exc

    event_type = ses_event.get("eventType") or ses_event.get("notificationType") or ""
    ses_message_id = ses_event.get("mail", {}).get("messageId", "")
    if not ses_message_id:
        logger.info("SES event without messageId; skipping")
        return

    handler = EVENT_HANDLERS.get(event_type, unknown)
    matching_logs = Q(provider="ses", provider_message_id=ses_message_id)
    correlation = _delivery_correlation(ses_event.get("mail", {}))
    if correlation and handler is not unknown:
        recipient_id, attempt, destinations = correlation
        matching_logs |= Q(
            pk=recipient_id,
            attempts=attempt,
            email_address__in=destinations,
            provider__in=["", "ses"],
            provider_message_id="",
        )
    campaign_ids = set()
    with transaction.atomic():
        # Retry/recovery lock job -> recipient -> campaign. Discover candidates
        # without a lock, then use that same order and recheck the event match.
        candidates = dict(RecipientLog.objects.filter(matching_logs).values_list("pk", "campaign_id"))
        jobs = {
            job.dedupe_key: job
            for job in BackgroundJob.objects.select_for_update()
            .filter(
                kind="mail.email_recipient",
                dedupe_key__in=[f"{campaign_id}:{log_id}" for log_id, campaign_id in candidates.items()],
            )
            .order_by("pk")
        }
        logs = list(RecipientLog.objects.select_for_update().filter(matching_logs, pk__in=candidates).order_by("pk"))
        for log in logs:
            job = jobs.get(f"{log.campaign_id}:{log.pk}")
            if log.last_sns_message_id and log.last_sns_message_id == sns_message_id:
                # Replays can also repair jobs left uncertain by older workers.
                if _reconcile_delivery_job(job, log):
                    campaign_ids.add(log.campaign_id)
                continue
            if not log.provider_message_id:
                # A verified provider event proves acceptance even if the send
                # response is still in flight or eventually times out. Retain
                # this association so later events use the ordinary ID lookup.
                log.provider = "ses"
                log.provider_message_id = ses_message_id
                log.sent_at = log.sent_at or timezone.now()
                log.status = "sent"
                log.error_message = ""
                log.uncertain_at = None
                log.save(
                    update_fields=[
                        "provider",
                        "provider_message_id",
                        "sent_at",
                        "status",
                        "error_message",
                        "uncertain_at",
                        "updated_at",
                    ]
                )
            handler(log, ses_event, sns_message_id)
            _reconcile_delivery_job(job, log)
            campaign_ids.add(log.campaign_id)
        if campaign_ids:
            from apps.mail.services.campaign.dispatch import aggregate_email_campaign

            for campaign_id in sorted(campaign_ids):
                aggregate_email_campaign(campaign_id)


def _reconcile_delivery_job(job, log) -> bool:
    """Finish the confirmed attempt while its job and recipient are locked."""
    if (
        job is None
        or job.status
        not in {
            BackgroundJob.Status.PROCESSING,
            BackgroundJob.Status.RETRY,
            BackgroundJob.Status.UNCERTAIN,
            BackgroundJob.Status.FAILED,
        }
        or job.attempts != log.attempts
        or not log.attempts
        or job.payload.get("recipient_log_id") != str(log.pk)
        or log.provider != "ses"
        or not log.provider_message_id
        or not log.last_sns_message_id
    ):
        return False
    if log.status in {"sent", "delivered"}:
        status, error = BackgroundJob.Status.SUCCEEDED, ""
    elif log.status in {"bounced", "complained", "rejected"}:
        status, error = BackgroundJob.Status.FAILED, "Recipient already has a terminal provider failure."
    else:
        return False

    if (
        job.status == status
        and job.completed_at is not None
        and job.last_error == error
        and all(
            value is None
            for value in (job.claim_token, job.claimed_at, log.claim_token, log.claimed_at, log.uncertain_at)
        )
    ):
        return False

    now = timezone.now()
    # Include PROCESSING: revoking its claim makes a returning worker's failure
    # or completion CAS a no-op, even when it already decided to report timeout.
    BackgroundJob.objects.filter(pk=job.pk).update(
        status=status,
        completed_at=job.completed_at if job.status == status and job.completed_at is not None else now,
        claim_token=None,
        claimed_at=None,
        last_error=error,
        updated_at=now,
    )
    RecipientLog.objects.filter(pk=log.pk).update(
        claim_token=None,
        claimed_at=None,
        uncertain_at=None,
        updated_at=now,
    )
    return True


def _delivery_correlation(mail):
    """Validate the application tags before matching a pre-send log."""
    tags = mail.get("tags", {})
    destinations = mail.get("destination", [])
    if not isinstance(tags, dict) or not isinstance(destinations, list):
        return None
    recipient_ids = tags.get("i2g_recipient_id", [])
    attempts = tags.get("i2g_delivery_attempt", [])
    if not isinstance(recipient_ids, list) or len(recipient_ids) != 1:
        return None
    if not isinstance(attempts, list) or len(attempts) != 1:
        return None
    try:
        recipient_id = UUID(str(recipient_ids[0]))
        attempt = int(attempts[0])
    except (ValueError, TypeError, AttributeError):
        return None
    if not 0 < attempt <= 32767:
        return None
    return recipient_id, attempt, [address for address in destinations if isinstance(address, str)]
