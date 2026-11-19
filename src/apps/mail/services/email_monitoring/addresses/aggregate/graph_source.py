"""Counting Microsoft Graph bounce reports into bounced-address rows, and linking each report to its campaigns."""

from collections import defaultdict
from datetime import timedelta

from django.conf import settings
from django.db.models.functions import Lower

from apps.core.models import EmailBounce
from apps.core.services.email.telemetry import text
from apps.mail.models import BouncedAddress, BouncedAddressCampaign, RecipientLog
from apps.mail.services.audience.suppression import normalize_address

from .sources import COUNT_FIELDS, Category, Match, Source, _reopen, locked_row

GRAPH_FIELDS = (
    "pk",
    "created_at",
    "received_at",
    "recipient",
    "classification",
    "category",
    "status_code",
    "reason",
    "diagnostic_code",
    "remote_mta",
    "campaign_id",
    "match_method",
    "trusted_recipient",
)

# The categories that reopen a dismissed address (strong evidence against it), when matched to the site's mail.
GRAPH_REOPEN = frozenset({Category.HARD, Category.MAILBOX_DISABLED})


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


def _trusted(bounce: dict) -> bool:
    return bounce["trusted_recipient"] and bounce["match_method"] == EmailBounce.MatchMethod.MESSAGE_ID


def _add_graph_bounce(row: BouncedAddress, bounce: dict) -> None:
    field = COUNT_FIELDS.get(bounce["classification"], "unknown_count")
    setattr(row, field, getattr(row, field) + 1)
    category = bounce["category"] if bounce["category"] in Category.values else Category.UNKNOWN
    counts = dict(row.category_counts or {})
    counts[category] = int(counts.get(category) or 0) + 1
    row.category_counts = counts
    at = bounce["received_at"]
    if row.graph_first_at is None or at < row.graph_first_at:
        row.graph_first_at = at
    if row.graph_last_at is None or at >= row.graph_last_at:
        row.graph_last_at = at
        row.last_classification = bounce["classification"][:16]
        row.last_category = category
        row.last_status_code = bounce["status_code"][:16]
        row.last_reason = text.clean(bounce["reason"], 255)
        row.last_diagnostic = text.scrub(bounce["diagnostic_code"], 1000)
        row.last_remote_mta = text.clean(bounce["remote_mta"], 255)
    matched = bounce["match_method"] != EmailBounce.MatchMethod.UNMATCHED
    if matched:
        row.matched_count += 1
    # Only a report matched to an email the site sent reopens: anyone can mail a report-shaped message.
    if _trusted(bounce) and category in GRAPH_REOPEN:
        if category == Category.HARD:
            row.trusted_graph_hard_count += 1
        else:
            row.trusted_graph_disabled_count += 1
        if row.trusted_graph_last_permanent_at is None or at > row.trusted_graph_last_permanent_at:
            row.trusted_graph_last_permanent_at = at
        code = bounce["status_code"] or "no status code"
        _reopen(row, f"New bounce report: {Category(category).label.lower()} ({code}).", at)


def _link_graph(row: BouncedAddress, campaign_id, match: str, at, category: str) -> None:
    category = category if category in Category.values else Category.UNKNOWN
    link, created = BouncedAddressCampaign.objects.get_or_create(
        bounced_address=row,
        campaign_id=campaign_id,
        source=Source.GRAPH,
        defaults={
            "match": match,
            "bounce_count": 1,
            # A likely event must never become retry evidence merely because a later event upgrades this aggregate
            # row's match label to exact.  Only each event that names the campaign exactly contributes here.
            "graph_category_counts": {category: 1} if match == Match.EXACT else {},
            "first_at": at,
            "last_at": at,
        },
    )
    if created:
        return
    link.bounce_count += 1
    if match == Match.EXACT:
        counts = dict(link.graph_category_counts or {})
        counts[category] = int(counts.get(category) or 0) + 1
        link.graph_category_counts = counts
    link.first_at = min(link.first_at or at, at)
    link.last_at = max(link.last_at or at, at)
    if match == Match.EXACT:
        link.match = Match.EXACT
    link.save(update_fields=["bounce_count", "graph_category_counts", "first_at", "last_at", "match", "updated_at"])


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
        row = locked_row(address)
        for bounce in bounces:
            _add_graph_bounce(row, bounce)
            if bounce["campaign_id"]:
                match = Match.EXACT if _trusted(bounce) else Match.LIKELY
                _link_graph(row, bounce["campaign_id"], match, bounce["received_at"], bounce["category"])
            elif bounce["pk"] in likely:
                _link_graph(row, likely[bounce["pk"]], Match.LIKELY, bounce["received_at"], bounce["category"])
        touched.append(row)
    return touched
