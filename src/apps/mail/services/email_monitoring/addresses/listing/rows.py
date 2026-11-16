"""The rows a Bounced addresses listing shows: its query, sort, page and per-status counts."""

from datetime import datetime, time, timedelta

from django.core.paginator import Paginator
from django.db.models import Count, F, Q
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.mail.models import BouncedAddress, BouncedAddressCampaign, EmailCampaign

from .filters import CATEGORIES, EVIDENCE, MEMBER_STATES, SORTS, SUPPRESSED, TYPES, Listing, Status


def _day_start(value: str):
    return timezone.make_aware(datetime.combine(parse_date(value), time.min))


def _conditions(filters: dict) -> list:
    """The ``Q`` conditions of the chosen filters (each value already checked against its choices)."""
    conditions = []
    for name, table in (("type", TYPES), ("category", CATEGORIES), ("member", MEMBER_STATES), ("evidence", EVIDENCE)):
        if filters[name]:
            conditions.append(table[filters[name]][1])
    if filters["suppressed"]:
        conditions.append(SUPPRESSED[filters["suppressed"]])
    if filters["role"]:
        conditions.append(Q(role=filters["role"]))
    if filters["suggestion"]:
        conditions.append(Q(suggestion="" if filters["suggestion"] == "none" else filters["suggestion"]))
    if filters["campaign"]:
        linked = BouncedAddressCampaign.objects.filter(campaign_id=filters["campaign"]).values("bounced_address_id")
        conditions.append(Q(pk__in=linked))
    if filters["q"]:
        query = filters["q"]
        conditions.append(
            Q(address__icontains=query) | Q(member__first_name__icontains=query) | Q(member__last_name__icontains=query)
        )
    return conditions


def _filtered(filters: dict):
    rows = BouncedAddress.objects.all()
    if filters["status"] != "all":
        rows = rows.filter(status=filters["status"])
    if filters["start"]:
        rows = rows.filter(last_bounce_at__gte=_day_start(filters["start"]))
    if filters["end"]:
        rows = rows.filter(last_bounce_at__lt=_day_start(filters["end"]) + timedelta(days=1))
    for condition in _conditions(filters):
        rows = rows.filter(condition)
    return rows


def rows_for(listing: Listing):
    rows = _filtered(listing.filters).select_related("member", "reviewed_by", "suppressed_by")
    rows = rows.annotate(
        hard_sort=F("hard_count") + F("ses_permanent_count"),
        report_sort=F("hard_count")
        + F("soft_count")
        + F("rejected_count")
        + F("delayed_count")
        + F("unknown_count")
        + F("ses_permanent_count")
        + F("ses_transient_count")
        + F("ses_undetermined_count")
        + F("complaint_count")
        + F("left_org_count"),
    )
    field = SORTS[listing.sort]
    ordering = F(field).desc(nulls_last=True) if listing.descending else F(field).asc(nulls_last=True)
    return rows.order_by(ordering, "address")


def paginate(rows, listing: Listing):
    return Paginator(rows, listing.page_size).get_page(listing.page)


def status_counts(filters: dict) -> dict:
    """How many addresses each status has under the other filters (for the status tabs)."""
    counts = dict(_filtered({**filters, "status": "all"}).values_list("status").annotate(n=Count("pk")).order_by())
    return {"all": sum(counts.values()), **{status: counts.get(status, 0) for status in Status.values}}


def campaign_options() -> list:
    """The campaigns at least one counted bounce is attributed to, newest first."""
    ids = BouncedAddressCampaign.objects.values("campaign_id")
    return list(
        EmailCampaign.objects.filter(pk__in=ids).order_by(F("sent_at").desc(nulls_last=True)).values("pk", "name")
    )
