"""What the active email provider's limits mean for a campaign, shown before it is sent."""

from math import ceil

from apps.core.models import EmailServiceConfig
from apps.core.models.base.service_credentials.microsoft_graph import GRAPH_DAILY_RECIPIENT_LIMIT
from apps.core.services.background_jobs import jobs_enabled


def format_duration(seconds: float) -> str:
    """A rounded, human-readable duration such as ``42 minutes`` or ``2 hours 5 minutes``."""
    minutes = max(1, round(seconds / 60))
    hours, minutes = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    return " ".join(parts)


def campaign_job_spacing(config=None) -> float:
    """Seconds between the recipient jobs of one queued email campaign.

    The worker claims jobs strictly by ``available_at``, and Microsoft Graph's per-minute ceiling makes a campaign
    take far longer than other queued work. Making each recipient due at its paced slot lets ticket emails, security
    notices and other job kinds queued meanwhile run between them. SES and SMTP keep every recipient due at once.
    """
    config = config or EmailServiceConfig.load()
    if config.provider != EmailServiceConfig.Provider.GRAPH:
        return 0.0
    rate = config.effective_send_rate
    return 1 / rate if rate > 0 else 0.0


def delivery_pacing_notice(config, recipient_count: int) -> dict | None:
    """A notice for the send-confirmation page, or None when the provider adds no limits worth showing.

    Only Microsoft Graph has any (about 30 messages per minute and 10,000 recipients per day for the whole
    mailbox). The page warns; it never blocks the send.
    """
    if config.provider != EmailServiceConfig.Provider.GRAPH or recipient_count <= 0:
        return None
    rate = config.effective_send_rate
    return {
        "provider": config.get_provider_display(),
        "rate": config.send_rate_display,
        "duration": format_duration(ceil(recipient_count / rate)) if rate > 0 else "",
        "daily_limit": GRAPH_DAILY_RECIPIENT_LIMIT,
        "over_daily_limit": recipient_count > GRAPH_DAILY_RECIPIENT_LIMIT,
        # Without the background worker a throttled recipient is recorded as failed and never retried.
        "retries_enabled": jobs_enabled(),
    }
