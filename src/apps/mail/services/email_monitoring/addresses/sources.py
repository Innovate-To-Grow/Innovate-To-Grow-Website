"""Counting one batch of each bounce source into ``BouncedAddress`` rows.

- **Microsoft Graph** (``core.EmailBounce``): a report row is never changed after it is saved, so each one is counted
  once, in creation order, and its count stays when the row is purged. The campaign is the matched email's
  (``exact``) or, for an unmatched report, the one campaign that mailed the address in the matching window before
  it (``likely``; none when several did).
- **Amazon SES** (``RecipientLog`` bounce and complaint events): a log is updated when an event arrives, so each log
  is kept as one ``BouncedAddressCampaign`` row (an upsert, so seeing it again changes nothing) and the address's SES
  counts are recounted from those rows.

A hard or rejected bounce, or a complaint, that arrives after an address was dismissed sets it back to open (queue
state only).
"""

from collections import defaultdict
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.db.models.functions import Lower

from apps.core.models import EmailBounce
from apps.core.services.email.telemetry import text
from apps.mail.models import BouncedAddress, BouncedAddressAction, BouncedAddressCampaign, RecipientLog
from apps.mail.services.suppression import normalize_address

Classification = EmailBounce.Classification
Source = BouncedAddressCampaign.Source
Match = BouncedAddressCampaign.Match
COUNT_FIELDS = {
    Classification.HARD: "hard_count",
    Classification.SOFT: "soft_count",
    Classification.REJECTED: "rejected_count",
    Classification.DELAYED: "delayed_count",
    Classification.UNKNOWN: "unknown_count",
}
GRAPH_FIELDS = (
    "pk",
    "created_at",
    "received_at",
    "recipient",
    "classification",
    "status_code",
    "reason",
    "diagnostic_code",
    "remote_mta",
    "campaign_id",
)
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
GRAPH_REOPEN = frozenset({Classification.HARD, Classification.REJECTED})


def after_cursor(rows, state, field: str):
    """``rows`` past the state's cursor, in (``field``, pk) order."""
    if state.cursor_at is not None:
        rows = rows.filter(
            Q(**{f"{field}__gt": state.cursor_at}) | Q(**{field: state.cursor_at, "pk__gt": state.cursor_id})
        )
    return rows.order_by(field, "pk")


def _locked_row(address: str) -> BouncedAddress:
    row, _created = BouncedAddress.objects.get_or_create(address=address)
    return BouncedAddress.objects.select_for_update().get(pk=row.pk)


def _reopen(row: BouncedAddress, why: str, at) -> None:
    """Reopen a dismissed address for a report that arrived after it was dismissed. A rebuild recounting older
    reports reopens nothing, and neither does a report when the dismissal's time is unknown."""
    if row.status != BouncedAddress.Status.DISMISSED or row.reviewed_at is None or at is None or at <= row.reviewed_at:
        return
    row.status = BouncedAddress.Status.OPEN
    row.resolution = ""
    BouncedAddressAction.objects.create(
        bounced_address=row,
        address=row.address,
        action=BouncedAddressAction.Action.REOPEN,
        actor_label="Automatic: queue state only",
        role_before=row.role,
        role_after=row.role,
        note=why[:500],
        member_id=row.member_id,
        member_ref=row.member_id,
    )


# --- Microsoft Graph -------------------------------------------------------------------------------------------------


def _likely_campaigns(bounces) -> dict:
    """``{bounce pk: campaign id}`` for unmatched reports whose address exactly one campaign mailed in the window."""
    bounces = [bounce for bounce in bounces if not bounce["campaign_id"] and normalize_address(bounce["recipient"])]
    if not bounces:
        return {}
    window = timedelta(hours=int(settings.EMAIL_MONITORING["bounce_match_window_hours"]))
    sends = defaultdict(list)
    logs = (
        RecipientLog.objects.annotate(normalized=Lower("email_address"))
        .filter(
            normalized__in={normalize_address(bounce["recipient"]) for bounce in bounces},
            sent_at__gte=min(bounce["received_at"] for bounce in bounces) - window,
            sent_at__lte=max(bounce["received_at"] for bounce in bounces),
        )
        .values_list("normalized", "campaign_id", "sent_at")
    )
    for address, campaign_id, sent_at in logs:
        sends[address].append((campaign_id, sent_at))
    found = {}
    for bounce in bounces:
        received = bounce["received_at"]
        campaigns = {
            campaign_id
            for campaign_id, sent_at in sends[normalize_address(bounce["recipient"])]
            if received - window <= sent_at <= received
        }
        if len(campaigns) == 1:
            found[bounce["pk"]] = campaigns.pop()
    return found


def _add_graph_bounce(row: BouncedAddress, bounce: dict) -> None:
    field = COUNT_FIELDS.get(bounce["classification"], "unknown_count")
    setattr(row, field, getattr(row, field) + 1)
    at = bounce["received_at"]
    if row.graph_first_at is None or at < row.graph_first_at:
        row.graph_first_at = at
    if row.graph_last_at is None or at >= row.graph_last_at:
        row.graph_last_at = at
        row.last_classification = bounce["classification"][:16]
        row.last_status_code = bounce["status_code"][:16]
        row.last_reason = text.clean(bounce["reason"], 255)
        row.last_diagnostic = text.scrub(bounce["diagnostic_code"], 1000)
        row.last_remote_mta = text.clean(bounce["remote_mta"], 255)
    if bounce["classification"] in GRAPH_REOPEN:
        code = bounce["status_code"] or "no status code"
        _reopen(row, f"New {bounce['classification']} bounce report ({code}).", at)


def _link_graph(row: BouncedAddress, campaign_id, match: str, at) -> None:
    link, created = BouncedAddressCampaign.objects.get_or_create(
        bounced_address=row,
        campaign_id=campaign_id,
        source=Source.GRAPH,
        defaults={"match": match, "bounce_count": 1, "first_at": at, "last_at": at},
    )
    if created:
        return
    link.bounce_count += 1
    link.first_at = min(link.first_at or at, at)
    link.last_at = max(link.last_at or at, at)
    if match == Match.EXACT:
        link.match = Match.EXACT
    link.save(update_fields=["bounce_count", "first_at", "last_at", "match", "updated_at"])


def count_graph(batch) -> list[BouncedAddress]:
    """Count a batch of report rows (``GRAPH_FIELDS`` dicts, in cursor order); return the rows it changed."""
    likely = _likely_campaigns(batch)
    grouped = defaultdict(list)
    for bounce in batch:
        address = normalize_address(bounce["recipient"])
        if address:
            grouped[address].append(bounce)
    touched = []
    # Rows are locked in address order, as every counting batch does, so two batches never wait on each other in a
    # cycle.
    for address, bounces in sorted(grouped.items()):
        row = _locked_row(address)
        for bounce in bounces:
            _add_graph_bounce(row, bounce)
            if bounce["campaign_id"]:
                _link_graph(row, bounce["campaign_id"], Match.EXACT, bounce["received_at"])
            elif bounce["pk"] in likely:
                _link_graph(row, likely[bounce["pk"]], Match.LIKELY, bounce["received_at"])
        touched.append(row)
    return touched


# --- Amazon SES ------------------------------------------------------------------------------------------------------


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
        row = _locked_row(address)
        for log in logs:
            _upsert_ses(row, log)
        recount_ses(row)
        touched.append(row)
    return touched
