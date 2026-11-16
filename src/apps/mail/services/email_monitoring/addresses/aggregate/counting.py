"""Counting each source's new reports into the bounced-address rows, one batch at a time from its cursor."""

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.models import EmailBounce
from apps.core.services.email.bounces.store import classify_unclassified
from apps.mail.models import (
    BounceAggregationState,
    BouncedAddress,
    BouncedAddressAction,
    BouncedAddressCampaign,
    RecipientLog,
)

from ..listing.matching import match_addresses, refresh_cached_links
from . import graph_source, notices, ses_source, sources
from .state import (
    COUNTED_FIELDS,
    GRAPH,
    GRAPH_COUNT_FIELDS,
    INBOUND,
    PARKED,
    SES,
    RunResult,
    _batch_size,
    _earliest,
    _latest,
    _locked_state,
    _settled,
    finish,
)


def _graph_rows(state, until=None):
    rows = EmailBounce.objects.all() if until is None else EmailBounce.objects.filter(created_at__lte=until)
    return sources.after_cursor(rows, state, "created_at")


def _ses_rows(state, until=None):
    rows = RecipientLog.objects.filter(Q(bounced_at__isnull=False) | Q(complained_at__isnull=False))
    if until is not None:
        rows = rows.filter(updated_at__lte=until)
    return sources.after_cursor(rows, state, "updated_at")


SOURCES = {
    GRAPH: (_graph_rows, graph_source.GRAPH_FIELDS, graph_source.count_graph, "created_at"),
    SES: (_ses_rows, ses_source.SES_FIELDS, ses_source.count_ses, "updated_at"),
    INBOUND: (notices.rows, notices.FIELDS, notices.count, "processed_at"),
}


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
        first_bounce_at=_earliest("ses_first_at", "left_org_first_at"),
        last_bounce_at=_latest("ses_last_at", "left_org_last_at"),
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
            size = min(size, max_rows - sum(result[name] for name in SOURCES))
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
    result = {GRAPH: 0, SES: 0, INBOUND: 0, "busy": False}
    for source in (GRAPH, SES, INBOUND):
        _drain(source, result, max_rows=max_rows, wait=wait, should_stop=should_stop)
    return result


def pending() -> int:
    """How many reports and SES events are not counted yet (including those still settling)."""
    total = 0
    for source, (rows_for, _fields, _count, _cursor) in SOURCES.items():
        state = BounceAggregationState.objects.filter(source=source).first() or BounceAggregationState(source=source)
        total += rows_for(state).count()
    return total
