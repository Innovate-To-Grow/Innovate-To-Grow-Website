"""Mirroring outbox job state into recipient logs and campaign totals."""

from django.db import transaction
from django.utils import timezone

from apps.core.models import BackgroundJob

from .channels import CHANNELS_BY_KIND, EMAIL, aggregate_email_campaign, aggregate_sms_campaign

# The outbox states a recipient log mirrors, with the message shown for each.
_MIRRORED_STATES = {
    BackgroundJob.Status.RETRY: ("retry", "Temporary delivery failure; retry scheduled."),
    BackgroundJob.Status.FAILED: ("failed", "Delivery failed before the provider confirmed acceptance."),
    BackgroundJob.Status.UNCERTAIN: ("uncertain", "Provider call outcome is uncertain; review before retrying."),
}
_FAILED_LOG_STATUSES = {"failed", "bounced", "complained", "rejected"}


def prepare_delivery_log_retry(job) -> None:
    """Mirror an explicit BackgroundJob retry into its recipient log."""
    sync_delivery_job_state(job)


def resolve_stale_delivery_job(job) -> str | None:
    """Prove completion from the recipient log after a worker crash."""

    log_id = job.payload.get("recipient_log_id")
    channel = CHANNELS_BY_KIND.get(job.kind)
    if not log_id or channel is None:
        return None
    status = channel.log_model.objects.select_for_update().filter(pk=log_id).values_list("status", flat=True).first()
    if status in channel.success_statuses:
        return BackgroundJob.Status.SUCCEEDED
    if status == "uncertain":
        return BackgroundJob.Status.UNCERTAIN
    if status == "retry":
        return BackgroundJob.Status.RETRY
    if status in _FAILED_LOG_STATUSES:
        return BackgroundJob.Status.FAILED
    return None


def sync_delivery_job_state(job) -> None:
    """Mirror retry/terminal outbox state into its recipient and campaign."""

    log_id = job.payload.get("recipient_log_id")
    if not log_id:
        return
    now = timezone.now()
    succeeded = job.status == BackgroundJob.Status.SUCCEEDED
    mapped = _MIRRORED_STATES.get(job.status)
    if mapped is None and not succeeded:
        return
    with transaction.atomic():
        current_job = BackgroundJob.objects.select_for_update().filter(pk=job.pk).first()
        if current_job is None or current_job.status != job.status or current_job.claim_token != job.claim_token:
            # ``job`` is an out-of-date retry/recovery snapshot. A newer worker
            # owns the row, so this mirror must not clear its recipient-log claim.
            return
        channel = CHANNELS_BY_KIND.get(job.kind)
        if channel is None:
            return
        log = channel.log_model.objects.filter(pk=log_id).first()
        if log is None:
            return
        if not succeeded:
            status, error = mapped
            channel.log_model.objects.filter(pk=log.pk).exclude(status__in=channel.terminal_statuses).update(
                status=status,
                available_at=job.available_at,
                claim_token=None,
                claimed_at=None,
                uncertain_at=now if status == "uncertain" else None,
                error_message=error,
                updated_at=now,
            )
        (aggregate_email_campaign if channel is EMAIL else aggregate_sms_campaign)(log.campaign_id)
