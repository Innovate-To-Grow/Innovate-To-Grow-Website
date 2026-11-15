"""Stage an upload as a batch, and keep the admin's choices for it until it is applied or discarded.

Creating a batch writes only the batch and its rows: no member data. Every save of choices carries the batch's
``choices_version`` and raises it, so a page loaded before another tab's save can neither overwrite those choices nor
be confirmed. Each changed row records who chose and when; bulk controls are also kept in the batch's activity.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils import timezone

from apps.authn.models import MemberImportBatch, MemberImportRow

from ...workbook.parsing import values_from_json, values_to_json
from ..analysis.resolution import Context
from ..analysis.rows import RowAnalysis, analyse_rows
from ..lookup.load import load_snapshot
from ..plan.actions import SKIP

Status = MemberImportBatch.Status
_FACT_KEYS_NOT_STORED = ("options", "default")


def import_setting(name: str):
    return settings.MEMBER_IMPORT[name]


def activity_event(user, action: str, detail: str = "") -> dict:
    return {
        "at": timezone.now().isoformat(),
        "by": str(user.pk) if user is not None else None,
        "by_name": (user.get_full_name() or str(user.pk)) if user is not None else "",
        "action": action,
        "detail": detail,
    }


def to_stored(analysis: RowAnalysis) -> dict:
    """The ``MemberImportRow`` fields for ``analysis``, its choice reset to the default."""
    return {
        "values": values_to_json(analysis.values),
        "status": analysis.status,
        "conflict": analysis.conflict,
        "analysis": {**analysis.facts, "options": analysis.options, "default": analysis.default},
        "candidates": analysis.slice,
        "risky": analysis.risky,
        "warnings": analysis.warnings,
        "fingerprint": analysis.fingerprint,
        "target_member_id": analysis.target if analysis.target in (analysis.slice.get("members") or {}) else None,
        "choice": analysis.default,
        "ticks": [],
    }


def stored_analysis(row: MemberImportRow) -> RowAnalysis:
    """The analysis a stored row was reviewed with."""
    data = row.analysis or {}
    return RowAnalysis(
        values=values_from_json(row.values or {"row": row.row_number}),
        status=row.status,
        conflict=row.conflict,
        facts={key: value for key, value in data.items() if key not in _FACT_KEYS_NOT_STORED},
        options=data.get("options", []),
        default=data.get("default", SKIP),
        warnings=row.warnings or [],
        risky=row.risky or {},
        slice=row.candidates or {},
        fingerprint=row.fingerprint,
    )


def create_batch(read, *, user, mode: str, password: str, ctx: Context) -> MemberImportBatch:
    """Analyse the parsed upload ``read`` (``reader.SheetRead``) and store it as a batch in review."""
    analyses = analyse_rows(read.rows, load_snapshot(read.rows), ctx)
    now = timezone.now()
    with transaction.atomic():
        batch = MemberImportBatch.objects.create(
            created_by=user,
            mode=mode,
            file_name=read.file_name,
            file_sha256=read.file_sha256,
            file_size=read.file_size,
            sheet_name=read.sheet_name[:255],
            row_count=len(read.rows),
            columns=read.columns,
            file_warnings=read.warnings,
            default_password_hash=make_password(password) if password else "",
            expires_at=now + timedelta(hours=import_setting("batch_lifetime_hours")),
            activity=[activity_event(user, "upload", f"{read.file_name}: {len(read.rows)} rows")],
        )
        MemberImportRow.objects.bulk_create(
            [MemberImportRow(batch=batch, row_number=a.row_number, **to_stored(a)) for a in analyses], batch_size=200
        )
    return batch


def repeat_uploads(sha256: str, *, exclude=None):
    """Batches of the same file still in review, or applied within ``repeat_warning_days``."""
    since = timezone.now() - timedelta(days=import_setting("repeat_warning_days"))
    query = MemberImportBatch.objects.filter(file_sha256=sha256).select_related("created_by", "applied_by")
    in_review = query.filter(status=Status.REVIEW, expires_at__gt=timezone.now())
    applied = query.filter(status=Status.APPLIED, applied_at__gte=since)
    found = list(in_review) + list(applied)
    return [batch for batch in found if exclude is None or batch.pk != exclude]


def forget_password(batch: MemberImportBatch) -> None:
    """Drop the upload's Default Password hash: it is kept only while the batch can still be applied."""
    batch.default_password_hash = ""  # nosec B105 - clears a stored hash; it is not a credential


def is_expired(batch: MemberImportBatch) -> bool:
    return batch.status == Status.EXPIRED or (batch.status == Status.REVIEW and batch.expires_at <= timezone.now())


def mark_expired(batch: MemberImportBatch) -> None:
    """An expired review keeps no password hash and can't be applied; the purge deletes it.

    ``batch`` is what a view read, maybe before an apply that started before ``expires_at`` committed. So this is an
    UPDATE conditioned on the stored status, never a save of that copy: an import applied meanwhile stays applied.
    """
    now = timezone.now()
    if batch.status == Status.REVIEW and batch.expires_at <= now:
        stored = MemberImportBatch.objects.filter(pk=batch.pk, status=Status.REVIEW, expires_at__lte=now)
        stored.update(status=Status.EXPIRED, default_password_hash="", updated_at=now)  # nosec B106 - clears a hash
        batch.refresh_from_db(fields=["status", "default_password_hash", "updated_at"])


def discard_batch(batch: MemberImportBatch, user) -> None:
    with transaction.atomic():
        locked = MemberImportBatch.objects.select_for_update().get(pk=batch.pk)
        if locked.status != Status.REVIEW:
            return
        locked.status = Status.DISCARDED
        forget_password(locked)
        locked.activity = [*locked.activity, activity_event(user, "discard")]
        locked.save(update_fields=["status", "default_password_hash", "activity", "updated_at"])
