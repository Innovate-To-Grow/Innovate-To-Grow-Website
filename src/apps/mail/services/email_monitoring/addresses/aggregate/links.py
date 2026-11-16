"""Keeping the cached member links of bounced addresses current, parking the Graph cursor, and rebuilding counts."""

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.core.services.email.bounces.store import reclassify_stored
from apps.mail.models import (
    BounceAggregationState,
    BouncedAddress,
    BouncedAddressCampaign,
)

from ..listing.matching import refresh_cached_links
from .state import (
    GRAPH,
    GRAPH_COUNT_FIELDS,
    LINKS,
    PARKED,
    PARKED_ID,
    REBUILT_COUNT_FIELDS,
    SES,
    _batch_size,
    _config,
    _locked_state,
)
from .suggestions import suggest


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
    stored: the counts of reports already purged are lost; review state, suppression, the action log and the
    left-the-organisation notices stay as they are. Returns how many reports changed category or classification."""
    zero = dict.fromkeys(REBUILT_COUNT_FIELDS, 0)
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
            first_bounce_at=F("left_org_first_at"),
            last_bounce_at=F("left_org_last_at"),
            suggestion="",
        )
        BouncedAddress.objects.filter(left_org_count__gt=0, suppressed_at__isnull=True).update(
            suggestion=BouncedAddress.Suggestion.LEFT_ORG
        )
        for state in states.values():
            state.cursor_at = state.cursor_id = None
            state.processed_total = 0
            state.save(update_fields=["cursor_at", "cursor_id", "processed_total", "updated_at"])
    return reclassified
