"""Keeping the bounced-address counts current: each source is read from its stored cursor, one bounded batch per
transaction, and the cursor moves with the counts, so every report is counted exactly once.

A run holds the source's state row (``select_for_update``) for each batch, so two runs never count the same rows; a
page load does not wait for it (``wait=False`` skips a source another run holds). Rows newer than
``EMAIL_MONITORING["address_settle_seconds"]`` wait for the next run: a report saved by a transaction that commits
late can then never fall behind the cursor.

It runs when the Bounced addresses page loads (a bounded batch) and in the background worker's hourly maintenance,
before the email telemetry retention purge, so counts are complete before reports are deleted. Counting only writes
``BouncedAddress`` rows and their campaign rows: never a member, a contact email or a subscription.

Before each Graph batch, the reports saved without a category (by the previous release while a deploy rolled out)
are classified. ``mail.0026`` parks the Graph cursor (``PARKED``, far in the future) when Graph reports had been
counted before categories existed: the previous release, still running while the deploy rolls out, then counts no
Graph report, and the first count by this release starts the Graph counts again from the stored reports, so every
address gets its category counts (recorded like a rebuild). **Rebuild counts** classifies every stored report again
with the current rules first, so a change to the rules reaches the reports and the counts.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.core.models import EmailBounce
from apps.core.services.email.bounces.store import classify_unclassified, reclassify_stored
from apps.mail.models import (
    BounceAggregationState,
    BouncedAddress,
    BouncedAddressAction,
    BouncedAddressCampaign,
    RecipientLog,
)

from . import sources
from .matching import match_addresses, refresh_cached_links
from .suggestions import suggest

GRAPH, SES = "graph", "ses"
# The state row whose cursor says where the hourly re-check of cached links continues.
LINKS = "links"
# A Graph cursor here or later is parked (``mail.0026``, ``park_graph``): no report is past it, so a release that
# predates categories counts nothing, and this release's next count starts the Graph counts again.
PARKED = datetime(9999, 12, 31, tzinfo=UTC)
# Its id half: the cursor query compares ids too (``sources.after_cursor``), so it must never be empty.
PARKED_ID = uuid.UUID(int=2**128 - 1)
GRAPH_COUNT_FIELDS = ("hard_count", "soft_count", "rejected_count", "delayed_count", "unknown_count")
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


def _graph_rows(state, until=None):
    rows = EmailBounce.objects.all() if until is None else EmailBounce.objects.filter(created_at__lte=until)
    return sources.after_cursor(rows, state, "created_at")


def _ses_rows(state, until=None):
    rows = RecipientLog.objects.filter(Q(bounced_at__isnull=False) | Q(complained_at__isnull=False))
    if until is not None:
        rows = rows.filter(updated_at__lte=until)
    return sources.after_cursor(rows, state, "updated_at")


SOURCES = {
    GRAPH: (_graph_rows, sources.GRAPH_FIELDS, sources.count_graph, "created_at"),
    SES: (_ses_rows, sources.SES_FIELDS, sources.count_ses, "updated_at"),
}


def finish(row: BouncedAddress) -> None:
    """Derive the cross-source dates and the suggestion from the counts."""
    firsts = [at for at in (row.graph_first_at, row.ses_first_at) if at is not None]
    lasts = [at for at in (row.graph_last_at, row.ses_last_at) if at is not None]
    row.first_bounce_at = min(firsts, default=None)
    row.last_bounce_at = max(lasts, default=None)
    row.suggestion = suggest(row)


def _locked_state(source: str, *, wait: bool):
    BounceAggregationState.objects.get_or_create(source=source)
    return BounceAggregationState.objects.select_for_update(skip_locked=not wait).filter(source=source).first()


def _reset_graph_counts() -> None:
    """Zero every address's Graph counts and drop its Graph campaign rows (its SES counts stay)."""
    BouncedAddressCampaign.objects.filter(source=BouncedAddressCampaign.Source.GRAPH).delete()
    BouncedAddress.objects.filter(graph_last_at__isnull=False).update(
        **dict.fromkeys(GRAPH_COUNT_FIELDS, 0),
        matched_count=0,
        category_counts={},
        graph_first_at=None,
        graph_last_at=None,
        **dict.fromkeys(("last_classification", "last_category", "last_status_code", "last_reason"), ""),
        last_diagnostic="",
        last_remote_mta="",
        first_bounce_at=F("ses_first_at"),
        last_bounce_at=F("ses_last_at"),
        suggestion="",
    )


def _prepare_graph(state) -> None:
    """Before a Graph batch: classify the reports saved without a category, and start the Graph counts again when the
    cursor is parked (after the upgrade to categories, or when the counts did not add up)."""
    classify_unclassified()
    if state.cursor_at is None or state.cursor_at < PARKED:
        return
    _reset_graph_counts()
    state.cursor_at = state.cursor_id = None
    state.processed_total = 0
    state.save(update_fields=["cursor_at", "cursor_id", "processed_total", "updated_at"])
    BouncedAddressAction.objects.create(
        action=BouncedAddressAction.Action.REBUILD,
        actor_label="Automatic: Graph counts started again from the stored reports",
        details={"source": GRAPH},
    )


def graph_counts_agree(row: BouncedAddress) -> bool:
    """Whether the row's Graph counts by classification and by category add up to the same number. Every report this
    release counts adds one to each; one counted by the release before categories (while a deploy rolled out) does
    not, and the next refresh then has the Graph counts started again."""
    by_category = sum(int(count or 0) for count in (row.category_counts or {}).values())
    return by_category == sum(getattr(row, name) for name in GRAPH_COUNT_FIELDS)


def park_graph() -> None:
    """Have the next Graph count start the Graph counts again from the stored reports."""
    BounceAggregationState.objects.update_or_create(
        source=GRAPH, defaults={"cursor_at": PARKED, "cursor_id": PARKED_ID}
    )


def count_batch(source: str, *, wait: bool = True, now=None, size: int | None = None) -> RunResult:
    """Count one batch of ``source`` past its cursor; ``busy`` when another run holds it (``wait=False`` only)."""
    rows_for, fields, count, cursor_field = SOURCES[source]
    now = now or timezone.now()
    size = max(1, int(size or _batch_size()))
    with transaction.atomic():
        state = _locked_state(source, wait=wait)
        if state is None:
            return RunResult(busy=True)
        if source == GRAPH:
            _prepare_graph(state)
        batch = list(rows_for(state, _settled(now)).values(*fields)[:size])
        if not batch:
            return RunResult()
        touched = count(batch)
        for row in touched:
            finish(row)
            row.save(update_fields=COUNTED_FIELDS)
        refresh_cached_links(touched, match_addresses(row.address for row in touched))
        state.cursor_at, state.cursor_id = batch[-1][cursor_field], batch[-1]["pk"]
        state.last_run_at = now
        state.processed_total += len(batch)
        state.save(update_fields=["cursor_at", "cursor_id", "last_run_at", "processed_total", "updated_at"])
    return RunResult(counted=len(batch))


def _drain(source: str, result: dict, *, max_rows, wait: bool, should_stop) -> None:
    """Count ``source`` batch by batch into ``result`` until it is done, the row budget is spent, or a stop."""
    while not (should_stop is not None and should_stop()):
        size = _batch_size()
        if max_rows is not None:
            size = min(size, max_rows - result[GRAPH] - result[SES])
        if size <= 0:
            return
        batch = count_batch(source, wait=wait, size=size)
        result[source] += batch.counted
        result["busy"] = result["busy"] or batch.busy
        if not batch.counted:
            return


def run(*, max_rows: int | None = None, wait: bool = True, should_stop=None) -> dict:
    """Count both sources until they are done, ``max_rows`` were counted, or ``should_stop()``.

    Returns how many rows each source counted and whether a source was busy (held by another run).
    """
    result = {GRAPH: 0, SES: 0, "busy": False}
    for source in (GRAPH, SES):
        _drain(source, result, max_rows=max_rows, wait=wait, should_stop=should_stop)
    return result


def _batch_size() -> int:
    return max(1, int(_config()["address_batch_size"]))


def pending() -> int:
    """How many reports and SES events are not counted yet (including those still settling)."""
    total = 0
    for source, (rows_for, _fields, _count, _cursor) in SOURCES.items():
        state = BounceAggregationState.objects.filter(source=source).first() or BounceAggregationState(source=source)
        total += rows_for(state).count()
    return total


def _refresh_rows(rows) -> int:
    if not all(graph_counts_agree(row) for row in rows):
        park_graph()
    changed = refresh_cached_links(rows)
    for row in rows:
        suggestion = suggest(row)
        if suggestion != row.suggestion:
            BouncedAddress.objects.filter(pk=row.pk).update(suggestion=suggestion)
            changed += 1
    return changed


def refresh_all(*, should_stop=None) -> int:
    """Re-check cached links and suggestions (members and contacts change outside this page), at most
    ``address_refresh_rows_per_run`` addresses per run, continuing where the last run stopped."""
    limit = max(1, int(_config()["address_refresh_rows_per_run"]))
    state, _created = BounceAggregationState.objects.get_or_create(source=LINKS)
    last_pk, done, changed = state.cursor_id, 0, 0
    while done < limit and not (should_stop is not None and should_stop()):
        rows = BouncedAddress.objects.order_by("pk")
        if last_pk is not None:
            rows = rows.filter(pk__gt=last_pk)
        batch = list(rows[: min(_batch_size(), limit - done)])
        if not batch:
            last_pk = None  # the end of the list: the next run starts again from the first address
            break
        changed += _refresh_rows(batch)
        done += len(batch)
        last_pk = batch[-1].pk
    BounceAggregationState.objects.filter(pk=state.pk).update(cursor_id=last_pk, last_run_at=timezone.now())
    return changed


def rebuild() -> int:
    """Classify every stored report again with the current rules, then start counting again from the records still
    stored: the counts of reports already purged are lost; review state, suppression and the action log stay as they
    are. Returns how many reports changed category or classification."""
    zero = {name: 0 for name in COUNTED_FIELDS if name.endswith("_count")}
    blank = dict.fromkeys(("last_classification", "last_category", "last_status_code", "last_reason"), "")
    with transaction.atomic():
        states = {source: _locked_state(source, wait=True) for source in (GRAPH, SES)}
        reclassified = reclassify_stored()
        BouncedAddressCampaign.objects.all().delete()
        BouncedAddress.objects.update(
            **zero,
            **blank,
            category_counts={},
            last_diagnostic="",
            last_remote_mta="",
            graph_first_at=None,
            graph_last_at=None,
            ses_first_at=None,
            ses_last_at=None,
            ses_last={},
            first_bounce_at=None,
            last_bounce_at=None,
            suggestion="",
        )
        for state in states.values():
            state.cursor_at = state.cursor_id = None
            state.processed_total = 0
            state.save(update_fields=["cursor_at", "cursor_id", "processed_total", "updated_at"])
    return reclassified
