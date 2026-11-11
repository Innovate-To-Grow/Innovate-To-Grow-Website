"""Retention of staged member imports (``settings.MEMBER_IMPORT``).

- A batch that was not applied (in review, discarded or expired) is deleted, with its rows, once it expires
  (``batch_lifetime_hours`` after the upload).
- An applied batch keeps each row's sheet values and member snapshot for ``values_retention_days``; then they are
  blanked, and the batch keeps only who chose what for each row and the outcome.
- An applied batch is deleted ``rows_retention_days`` after it was applied. The members' History (LogEntry) stays.

It runs in bounded passes: on each visit to the upload page, and in the background worker's hourly maintenance.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.authn.models import MemberImportBatch, MemberImportRow

Status = MemberImportBatch.Status
_UNAPPLIED = (Status.REVIEW, Status.DISCARDED, Status.EXPIRED)


def purge_member_imports(*, now=None, should_stop=None, max_passes: int | None = None) -> dict[str, int]:
    """Delete expired and old batches and blank old sheet values; return the counts. ``max_passes`` bounds the work
    (``None``: until done); ``should_stop`` ends it after the pass in flight."""
    now = now or timezone.now()
    config = settings.MEMBER_IMPORT
    size = config["purge_batch_size"]
    steps = (
        ("expired", MemberImportBatch.objects.filter(status__in=_UNAPPLIED, expires_at__lte=now), _delete),
        (
            "blanked",
            MemberImportBatch.objects.filter(
                status=Status.APPLIED,
                values_purged_at__isnull=True,
                applied_at__lte=now - timedelta(days=config["values_retention_days"]),
            ),
            lambda ids: _blank(ids, now),
        ),
        (
            "deleted",
            MemberImportBatch.objects.filter(
                status=Status.APPLIED, applied_at__lte=now - timedelta(days=config["rows_retention_days"])
            ),
            _delete,
        ),
    )
    counts = {name: 0 for name, _query, _action in steps}
    passes = 0
    for name, query, action in steps:
        while max_passes is None or passes < max_passes:
            if should_stop is not None and should_stop():
                return counts
            ids = list(query.order_by("created_at").values_list("pk", flat=True)[:size])
            if not ids:
                break
            counts[name] += action(ids)
            passes += 1
    return counts


def _delete(ids) -> int:
    with transaction.atomic():
        MemberImportBatch.objects.filter(pk__in=ids).delete()
    return len(ids)


def _blank(ids, now) -> int:
    with transaction.atomic():
        MemberImportRow.objects.filter(batch_id__in=ids).update(values={}, candidates={}, risky={}, warnings=[])
        MemberImportBatch.objects.filter(pk__in=ids).update(values_purged_at=now, updated_at=now)
    return len(ids)
