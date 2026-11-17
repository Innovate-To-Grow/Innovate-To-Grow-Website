"""What every bounced-address count run shares: the sources' names, the parked cursor, the counted fields, the
run result and the per-source state row."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.db.models.functions import Coalesce, Greatest, Least

from apps.mail.models import (
    BounceAggregationState,
    BouncedAddress,
)

from .suggestions import suggest

GRAPH, SES, INBOUND = "graph", "ses", "inbound"
# The state row whose cursor says where the hourly re-check of cached links continues.
LINKS = "links"
# A Graph cursor here or later is parked (``mail.0026``, ``park_graph``): no report is past it, so a release that
# predates categories counts nothing, and this release's next count starts the Graph counts again.
PARKED = datetime(9999, 12, 31, tzinfo=UTC)
# Its id half: the cursor query compares ids too (``sources.after_cursor``), so it must never be empty.
PARKED_ID = uuid.UUID(int=2**128 - 1)
GRAPH_COUNT_FIELDS = ("hard_count", "soft_count", "rejected_count", "delayed_count", "unknown_count")
# The counts a rebuild starts again (the left-the-organisation notices stay).
REBUILT_COUNT_FIELDS = (
    *GRAPH_COUNT_FIELDS,
    "matched_count",
    "ses_permanent_count",
    "ses_transient_count",
    "ses_undetermined_count",
    "complaint_count",
)
COUNTED_FIELDS = [
    "hard_count",
    "soft_count",
    "rejected_count",
    "delayed_count",
    "unknown_count",
    "matched_count",
    "category_counts",
    "graph_first_at",
    "graph_last_at",
    "last_classification",
    "last_category",
    "last_status_code",
    "last_reason",
    "last_diagnostic",
    "last_remote_mta",
    "ses_permanent_count",
    "ses_transient_count",
    "ses_undetermined_count",
    "complaint_count",
    "ses_first_at",
    "ses_last_at",
    "ses_last",
    "left_org_count",
    "left_org_first_at",
    "left_org_last_at",
    "left_org_contact",
    "left_org_contact_kind",
    "left_org_contact_name",
    "left_org_contact_phone",
    "left_org_ticket",
    "first_bounce_at",
    "last_bounce_at",
    "status",
    "resolution",
    "suggestion",
    "updated_at",
]


@dataclass
class RunResult:
    counted: int = 0
    busy: bool = False


def _config() -> dict:
    return settings.EMAIL_MONITORING


def _settled(now):
    return now - timedelta(seconds=int(_config()["address_settle_seconds"]))


def _earliest(*fields):
    """The earliest non-null of the date ``fields``, or null (``Least`` alone is null on SQLite when any is)."""
    values = [Coalesce(field, *(other for other in fields if other != field)) for field in fields]
    return Least(*values)


def _latest(*fields):
    values = [Coalesce(field, *(other for other in fields if other != field)) for field in fields]
    return Greatest(*values)


def finish(row: BouncedAddress) -> None:
    """Derive the cross-source dates and the suggestion from the counts."""
    firsts = [at for at in (row.graph_first_at, row.ses_first_at, row.left_org_first_at) if at is not None]
    lasts = [at for at in (row.graph_last_at, row.ses_last_at, row.left_org_last_at) if at is not None]
    row.first_bounce_at = min(firsts, default=None)
    row.last_bounce_at = max(lasts, default=None)
    row.suggestion = suggest(row)


def _locked_state(source: str, *, wait: bool):
    BounceAggregationState.objects.get_or_create(source=source)
    return BounceAggregationState.objects.select_for_update(skip_locked=not wait).filter(source=source).first()


def _batch_size() -> int:
    return max(1, int(_config()["address_batch_size"]))
