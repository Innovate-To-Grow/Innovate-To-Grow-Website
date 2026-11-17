"""What the Bounced addresses list can be filtered and sorted by, and reading those choices from the request."""

import uuid
from dataclasses import dataclass

from django.db.models import Q
from django.utils.dateparse import parse_date

from apps.core.models import EmailBounce
from apps.mail.models import BouncedAddress

from ...dashboard.log import PAGE_SIZES

Category = EmailBounce.Category
Status = BouncedAddress.Status
STATUS_FILTERS = (*Status.values, "all")
TYPES = {
    "hard": ("Has a hard bounce", Q(hard_count__gt=0) | Q(ses_permanent_count__gt=0)),
    "soft": ("Has a soft bounce", Q(soft_count__gt=0) | Q(ses_transient_count__gt=0)),
    "rejected": ("Has a rejection (spam, relay or policy)", Q(rejected_count__gt=0)),
    "delayed": ("Has a delay report", Q(delayed_count__gt=0)),
    "unknown": ("Has an unknown status", Q(unknown_count__gt=0) | Q(ses_undetermined_count__gt=0)),
    "complaint": ("Has a spam complaint", Q(complaint_count__gt=0)),
    "left_org": ("Has a left-the-organisation notice", Q(left_org_count__gt=0)),
    "left_org_contact": (
        "Left-the-organisation contact for manual review",
        Q(left_org_contact__gt="") | Q(left_org_contact_name__gt="") | Q(left_org_contact_phone__gt=""),
    ),
}
# "Has a report of this category": Graph reports, and the SES bounce type that means the same where there is one.
SES_CATEGORY = {
    Category.HARD: ("SES permanent", Q(ses_permanent_count__gt=0)),
    Category.TRANSIENT: ("SES transient", Q(ses_transient_count__gt=0)),
    Category.UNKNOWN: ("SES undetermined", Q(ses_undetermined_count__gt=0)),
}


def _category_filter(value: str, label: str) -> tuple[str, Q]:
    condition = Q(category_counts__has_key=value)
    if value in SES_CATEGORY:
        ses_label, ses_condition = SES_CATEGORY[value]
        return f"{label} (or {ses_label})", condition | ses_condition
    return label, condition


CATEGORIES = {value: _category_filter(value, label) for value, label in Category.choices}
MEMBER_STATES = {
    "yes": ("Has a member", Q(member__isnull=False)),
    "no": ("No member", Q(member__isnull=True)),
    "active": ("Member active", Q(member__is_active=True)),
    "inactive": ("Member inactive", Q(member__is_active=False)),
    "staff": ("Member is staff", Q(member__is_staff=True) | Q(member__is_superuser=True)),
}
SUPPRESSED = {"yes": Q(suppressed_at__isnull=False), "no": Q(suppressed_at__isnull=True)}
_SES_EVENTS = (
    Q(ses_permanent_count__gt=0)
    | Q(ses_transient_count__gt=0)
    | Q(ses_undetermined_count__gt=0)
    | Q(complaint_count__gt=0)
)
_MATCHED = Q(matched_count__gt=0) | Q(left_org_count__gt=0) | _SES_EVENTS
EVIDENCE = {
    "matched": ("Matched to the site's mail (or SES)", _MATCHED),
    "unmatched": ("Unmatched reports only", ~_MATCHED),
}
SORTS = {
    "last": "last_bounce_at",
    "first": "first_bounce_at",
    "address": "address",
    "hard": "hard_sort",
    "reports": "report_sort",
    "category": "last_category",
    "status": "status",
    "role": "role",
}


@dataclass(frozen=True)
class Listing:
    sort: str
    descending: bool
    page_size: int
    page: str
    filters: dict

    def query(self) -> dict:
        """The filters as query parameters (empty values left out)."""
        return {key: value for key, value in self.filters.items() if value}


def _choice(params, name: str, allowed) -> str:
    value = str(params.get(name) or "")
    return value if value in allowed else ""


def _uuid(value) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        return ""


def _date(params, name: str) -> str:
    """A ``YYYY-MM-DD`` filter value, or "" (not a real date, or a year so far off that a day bound would overflow)."""
    try:
        parsed = parse_date(str(params.get(name) or ""))
    except ValueError:
        return ""
    return parsed.isoformat() if parsed and 1900 <= parsed.year <= 9998 else ""


def parse_listing(params) -> Listing:
    status = str(params.get("status") or Status.OPEN)
    filters = {
        "q": str(params.get("q") or "").strip()[:200],
        "status": status if status in STATUS_FILTERS else Status.OPEN,
        "type": _choice(params, "type", TYPES),
        "category": _choice(params, "category", CATEGORIES),
        "role": _choice(params, "role", BouncedAddress.Role.values),
        "member": _choice(params, "member", MEMBER_STATES),
        "suppressed": _choice(params, "suppressed", SUPPRESSED),
        "evidence": _choice(params, "evidence", EVIDENCE),
        "suggestion": _choice(params, "suggestion", (*BouncedAddress.Suggestion.values, "none")),
        "campaign": _uuid(params.get("campaign")),
        "start": _date(params, "start"),
        "end": _date(params, "end"),
    }
    sort = str(params.get("sort") or "last")
    try:
        page_size = int(params.get("page_size") or 50)
    except (TypeError, ValueError):
        page_size = 50
    return Listing(
        sort=sort if sort in SORTS else "last",
        descending=str(params.get("dir") or "desc") != "asc",
        page_size=page_size if page_size in PAGE_SIZES else 50,
        page=str(params.get("page") or "1"),
        filters=filters,
    )
