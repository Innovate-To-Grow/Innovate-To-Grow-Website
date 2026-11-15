"""Counting Amazon SES bounce and complaint events into bounced-address rows."""

from collections import defaultdict

from apps.core.services.email.telemetry import text
from apps.mail.models import BouncedAddress, BouncedAddressCampaign
from apps.mail.services.audience.suppression import normalize_address

from .sources import Match, Source, _reopen, locked_row

SES_FIELDS = (
    "pk",
    "updated_at",
    "email_address",
    "campaign_id",
    "bounced_at",
    "complained_at",
    "bounce_type",
    "bounce_subtype",
    "diagnostic_code",
)


def _upsert_ses(row: BouncedAddress, log: dict) -> None:
    events = [at for at in (log["bounced_at"], log["complained_at"]) if at is not None]
    values = {
        "match": Match.EXACT,
        "bounce_count": 1,
        "first_at": min(events),
        "last_at": max(events),
        "ses_bounce_type": (log["bounce_type"] or "")[:16],
        "ses_bounce_subtype": (log["bounce_subtype"] or "")[:32],
        "ses_diagnostic": text.scrub(log["diagnostic_code"], 500),
        "ses_bounced_at": log["bounced_at"],
        "ses_complained_at": log["complained_at"],
    }
    link = BouncedAddressCampaign.objects.filter(
        bounced_address=row, campaign_id=log["campaign_id"], source=Source.SES
    ).first()
    if link is None:
        link = BouncedAddressCampaign(bounced_address=row, campaign_id=log["campaign_id"], source=Source.SES)
    new_permanent = values["ses_bounce_type"] == "Permanent" and link.ses_bounced_at is None and log["bounced_at"]
    new_complaint = link.ses_complained_at is None and log["complained_at"] is not None
    for name, value in values.items():
        setattr(link, name, value)
    link.save()
    if new_permanent:
        _reopen(row, "New permanent bounce (Amazon SES).", log["bounced_at"])
    elif new_complaint:
        _reopen(row, "New spam complaint (Amazon SES).", log["complained_at"])


def recount_ses(row: BouncedAddress) -> None:
    """Set the address's SES counts and latest SES event from its SES campaign rows."""
    links = list(row.campaign_links.filter(source=Source.SES).order_by("last_at"))
    bounced = [link for link in links if link.ses_bounced_at is not None]
    row.ses_permanent_count = sum(1 for link in bounced if link.ses_bounce_type == "Permanent")
    row.ses_transient_count = sum(1 for link in bounced if link.ses_bounce_type == "Transient")
    row.ses_undetermined_count = len(bounced) - row.ses_permanent_count - row.ses_transient_count
    row.complaint_count = sum(1 for link in links if link.ses_complained_at is not None)
    row.ses_first_at = min((link.first_at for link in links), default=None)
    row.ses_last_at = links[-1].last_at if links else None
    if not links:
        row.ses_last = {}
        return
    last = links[-1]
    complaint_last = last.ses_complained_at is not None and (
        last.ses_bounced_at is None or last.ses_complained_at >= last.ses_bounced_at
    )
    row.ses_last = {
        "event": "complaint" if complaint_last else "bounce",
        "type": last.ses_bounce_type,
        "subtype": last.ses_bounce_subtype,
        "diagnostic": last.ses_diagnostic,
        "campaign_id": str(last.campaign_id),
    }


def count_ses(batch) -> list[BouncedAddress]:
    """Record a batch of recipient logs (``SES_FIELDS`` dicts); return the rows it changed."""
    grouped = defaultdict(list)
    for log in batch:
        address = normalize_address(log["email_address"])
        if address:
            grouped[address].append(log)
    touched = []
    for address, logs in sorted(grouped.items()):
        row = locked_row(address)
        for log in logs:
            _upsert_ses(row, log)
        recount_ses(row)
        touched.append(row)
    return touched
