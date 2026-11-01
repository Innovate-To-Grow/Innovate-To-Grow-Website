"""What the delivery limits mean for a campaign, shown before it is sent."""

from math import ceil

from apps.core.services.background_jobs import jobs_enabled
from apps.core.services.delivery_rates import Family, active_target, channel_status
from apps.core.services.delivery_rates.rules.defaults import section
from apps.core.services.delivery_rates.status_text import number


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


def _identity_status(target):
    status = channel_status(target.channel)
    found = next((item for item in status.identities if item.identity == target.identity), status.identities[0])
    return status, found


def delivery_pacing_notice(config, recipient_count: int) -> dict | None:
    """A notice for the send-confirmation page, or None when there is nothing to send or email is not set up.

    A campaign goes on the bulk lane: at most ``lanes.bulk_share`` of the email channel's current rate (Mail →
    Delivery Rates), and only the campaign share of each rolling 24-hour limit. The page warns; it never blocks the
    send.
    """
    target = active_target(Family.EMAIL)
    if recipient_count <= 0 or target is None:
        return None
    status, identity = _identity_status(target)
    bulk_rate = identity.rate.rate * section("lanes")["bulk_share"]
    per_second = bulk_rate / identity.rate.window
    daily = next((limit for limit in identity.limits if limit.name == "daily_limit"), None)
    return {
        "provider": config.get_provider_display(),
        "rate": f"{number(bulk_rate)} {status.unit}",
        "now": identity.headline,
        "duration": format_duration(ceil(recipient_count / per_second)) if per_second > 0 else "",
        "daily_limit": daily.limit if daily else None,
        "campaign_daily_limit": daily.bulk_usable if daily else None,
        "over_daily_limit": bool(daily) and recipient_count > daily.bulk_usable,
        # Without the background worker a campaign is sent by the web server itself and paused by a long hold.
        "retries_enabled": jobs_enabled(),
    }


def email_send_rate_line() -> str:
    """The active email channel's live status line ("Now: … · Smart · …"), for the delivery overview pages."""
    target = active_target(Family.EMAIL)
    if target is None:
        return "Not configured"
    return _identity_status(target)[1].headline
