"""The email log and the bounce list: server-side filtering, sorting and pagination over the indexed columns.

Every filter value is checked against its choices before it reaches the ORM, and the sort is one of a fixed set of
columns, so request parameters never name a field or a lookup.
"""

import uuid
from dataclasses import dataclass

from django.core.paginator import Paginator
from django.db.models import Q

from apps.core.models import EmailBounce, EmailCategory, OutboundEmail
from apps.core.services.email.telemetry import KIND_LABELS

from .scope import PROVIDERS, Scope

PAGE_SIZES = (25, 50, 100)
EMAIL_SORTS = {
    "created": "created_at",
    "recipient": "recipient",
    "category": "category",
    "status": "status",
    "delivery": "delivery_status",
    "attempts": "attempt_count",
    "duration": "total_duration_ms",
}
BOUNCE_SORTS = {
    "received": "received_at",
    "recipient": "recipient",
    "classification": "classification",
    "status": "status_code",
    "match": "match_method",
}
# The error kinds the telemetry records (its labels' keys).
ERROR_KINDS = tuple(KIND_LABELS)


@dataclass(frozen=True)
class Listing:
    sort: str
    descending: bool
    page_size: int
    page: str
    filters: dict


def _choice(params, name: str, allowed) -> str:
    value = str(params.get(name) or "")
    return value if value in allowed else ""


def _uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return None


def _listing(params, sorts: dict, default_sort: str, filters: dict) -> Listing:
    sort = str(params.get("sort") or default_sort)
    try:
        page_size = int(params.get("page_size") or 50)
    except (TypeError, ValueError):
        page_size = 50
    return Listing(
        sort=sort if sort in sorts else default_sort,
        descending=str(params.get("dir") or "desc") != "asc",
        page_size=page_size if page_size in PAGE_SIZES else 50,
        page=str(params.get("page") or "1"),
        filters=filters,
    )


def email_listing(params) -> Listing:
    filters = {
        "q": str(params.get("q") or "").strip()[:200],
        "category": _choice(params, "category", EmailCategory.values),
        "status": _choice(params, "status", OutboundEmail.Status.values),
        "delivery": _choice(params, "delivery", OutboundEmail.DeliveryStatus.values),
        "error": _choice(params, "error", ERROR_KINDS),
        "campaign": str(_uuid(str(params.get("campaign") or "")) or ""),
        "retried": "1" if params.get("retried") == "1" else "",
    }
    return _listing(params, EMAIL_SORTS, "created", filters)


def _search(rows, query: str, fields: tuple[str, ...]):
    if not query:
        return rows
    as_uuid = _uuid(query)
    if as_uuid is not None:
        return rows.filter(Q(pk=as_uuid) | Q(correlation_id=as_uuid) | Q(campaign_id=as_uuid))
    condition = Q()
    for field in fields:
        condition |= Q(**{f"{field}__icontains": query})
    return rows.filter(condition)


def email_rows(scope: Scope, listing: Listing):
    filters = listing.filters
    rows = OutboundEmail.objects.filter(created_at__gte=scope.start, created_at__lt=scope.end)
    if scope.provider in PROVIDERS:
        rows = rows.filter(provider=scope.provider)
    if filters["category"]:
        rows = rows.filter(category=filters["category"])
    else:
        rows = rows.exclude(category=EmailCategory.ACCESS_CHECK)
    for name, field in (("status", "status"), ("delivery", "delivery_status"), ("error", "last_error_kind")):
        if filters[name]:
            rows = rows.filter(**{field: filters[name]})
    if filters["campaign"]:
        rows = rows.filter(campaign_id=filters["campaign"])
    if filters["retried"]:
        rows = rows.filter(attempt_count__gt=1)
    if filters["q"]:
        rows = _search(rows, filters["q"], ("recipient", "subject", "internet_message_id", "last_error"))
    return _ordered(rows, EMAIL_SORTS, listing)


def bounce_listing(params) -> Listing:
    filters = {
        "q": str(params.get("q") or "").strip()[:200],
        "classification": _choice(params, "classification", EmailBounce.Classification.values),
        "match": _choice(params, "match", EmailBounce.MatchMethod.values),
    }
    return _listing(params, BOUNCE_SORTS, "received", filters)


def bounce_rows(scope: Scope, listing: Listing):
    filters = listing.filters
    rows = scope.bounces().select_related("email")
    if filters["classification"]:
        rows = rows.filter(classification=filters["classification"])
    if filters["match"]:
        rows = rows.filter(match_method=filters["match"])
    if filters["q"]:
        as_uuid = _uuid(filters["q"])
        if as_uuid is not None:
            rows = rows.filter(Q(pk=as_uuid) | Q(email_id=as_uuid) | Q(campaign_id=as_uuid))
        else:
            rows = _search(rows, filters["q"], ("recipient", "status_code", "reason", "original_subject"))
    return _ordered(rows, BOUNCE_SORTS, listing)


def _ordered(rows, sorts: dict, listing: Listing):
    field = sorts[listing.sort]
    return rows.order_by(f"-{field}" if listing.descending else field, "-pk")


def paginate(rows, listing: Listing):
    return Paginator(rows, listing.page_size).get_page(listing.page)
