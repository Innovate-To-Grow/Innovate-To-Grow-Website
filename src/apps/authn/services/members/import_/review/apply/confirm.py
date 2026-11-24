"""Apply a reviewed import: every row in one transaction, all or nothing.

The batch row is locked first, so a double click, a second tab or a browser resubmit waits and then finds the batch
applied. The members the review read are locked in primary-key order (the self-service contact services lock the
member row too, so a member editing their addresses waits instead of racing). Then every row is analysed again from
freshly read records. If any row's records changed since the review (its fingerprint differs), or a choice is no longer
allowed, nothing is applied: those rows go back to review with their choices reset. The ticked deactivations are
checked together against the Admin lockout rules. A row that fails to write rolls everything back, and the batch stays
in review with the reason in ``last_error``.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field

from django.contrib.auth.hashers import make_password
from django.db import DatabaseError, transaction
from django.utils import timezone

from apps.authn.models import MemberImportBatch, MemberImportRow

from ...workbook.parsing import generate_random_password, values_from_json
from ..analysis.choices import allowed_values
from ..analysis.resolution import INVALID, Context
from ..analysis.rows import analyse_rows
from ..lookup.load import load_snapshot
from ..plan.actions import SKIP
from ..staging.batches import activity_event, forget_password, to_stored
from ..staging.selection import selection_problems, tick_items
from .execute import RowWriteError, log_batch
from .rows import RowOutcome, deactivation_refusal, lock_members, run_import

logger = logging.getLogger(__name__)


@dataclass
class ApplyResult:
    status: str
    message: str = ""
    rows: list[int] = field(default_factory=list)


class _Stale(Exception):
    def __init__(self, fresh, changed: list[int]):
        super().__init__(f"{len(changed)} rows changed")
        self.fresh = fresh
        self.changed = changed


def changed_rows(stored_rows, fresh) -> list[int]:
    """Rows whose records changed since the review, whose warnings differ from the ones the review showed (a cell set
    aside differently, for example by a newer rule), or whose choice or ticks are no longer allowed."""
    changed = []
    for row, analysis in zip(stored_rows, fresh, strict=True):
        enabled = {item["id"] for item in tick_items(analysis, row.choice) if item["enabled"]}
        if (
            row.fingerprint != analysis.fingerprint
            or (row.status, row.conflict) != (analysis.status, analysis.conflict)
            or (row.warnings or []) != analysis.warnings
            or (analysis.status != INVALID and row.choice not in allowed_values(analysis.options))
            or not set(row.ticks) <= enabled
        ):
            changed.append(row.row_number)
    return changed


def apply_batch(batch_id, *, user, version: int, ctx: Context) -> ApplyResult:
    """Apply a batch for ``user`` (an Admin: the view checks). See the module docstring."""
    try:
        with transaction.atomic():
            batch = MemberImportBatch.objects.select_for_update().get(pk=batch_id)
            if batch.status != MemberImportBatch.Status.REVIEW:
                return ApplyResult("already")
            refusal = _refusal(batch, version)
            if refusal:
                return ApplyResult("refused", refusal)
            return _apply_locked(batch, user, ctx)
    except _Stale as exc:
        _send_back(batch_id, exc.fresh, exc.changed, user)
        return ApplyResult("stale", f"{len(exc.changed)} row(s) changed since the review", exc.changed)
    except RowWriteError as exc:
        _note_error(batch_id, str(exc), user)
        return ApplyResult("error", str(exc), [exc.row_number])
    except DatabaseError as exc:
        # A write the re-read records could not foresee: typically an address or number another request created after
        # the snapshot, which trips its unique constraint. The transaction rolled back, so nothing was written; send
        # the batch back to the review with the reason instead of failing the request.
        logger.exception("Member import %s: the apply hit a database error and was rolled back", batch_id)
        message = (
            f"A database error stopped the import ({exc.__class__.__name__}), probably a record that changed at the "
            "same moment. Check the review and confirm again"
        )
        _note_error(batch_id, message, user)
        return ApplyResult("error", message)


def _refusal(batch: MemberImportBatch, version: int) -> str:
    if batch.expires_at <= timezone.now():
        return "This review has expired. Upload the file again to start a new one."
    if version != batch.choices_version:
        return "The choices changed after this page was loaded (in another tab?). Check the summary and confirm again."
    return ""


def _apply_locked(batch: MemberImportBatch, user, ctx: Context) -> ApplyResult:
    stored = list(batch.rows.order_by("row_number"))
    member_ids = {member_id for row in stored for member_id in (row.candidates.get("members") or {})}
    members = lock_members(member_ids)
    values = [values_from_json(row.values) for row in stored]
    snapshot = load_snapshot(values)
    fresh = analyse_rows(values, snapshot, ctx)
    changed = changed_rows(stored, fresh)
    if changed:
        raise _Stale(fresh, changed)
    selections = {row.row_number: (row.choice, row.ticks) for row in stored}
    problem = next(iter(selection_problems(fresh, selections, snapshot)), "")
    problem = problem or deactivation_refusal(fresh, selections, snapshot, members, user)
    if problem:
        return ApplyResult("refused", problem)
    password_hash = batch.default_password_hash or make_password(generate_random_password())
    outcomes = run_import(
        fresh,
        selections,
        snapshot,
        password_hash=password_hash,
        members=members,
        actor_id=user.pk,
        label=batch.short_id,
    )
    _record(batch, stored, outcomes, user)
    return ApplyResult("applied")


def _record(batch: MemberImportBatch, stored, outcomes: list[RowOutcome], user) -> None:
    counts: Counter = Counter()
    risky: Counter = Counter()
    for row, outcome in zip(stored, outcomes, strict=True):
        counts[outcome.outcome] += 1
        risky.update({kind: len(items) for kind, items in outcome.listed.items()})
        row.outcome = outcome.outcome
        row.outcome_detail = "\n".join([*outcome.changes, *outcome.notes] or [outcome.reason])
        row.result_member = outcome.member
        row.updated_at = timezone.now()
    MemberImportRow.objects.bulk_update(
        stored, ["outcome", "outcome_detail", "result_member", "updated_at"], batch_size=500
    )
    now = timezone.now()
    batch.status = MemberImportBatch.Status.APPLIED
    batch.applied_at, batch.applied_by = now, user
    batch.summary = {"outcomes": dict(counts), "risky": dict(risky)}
    forget_password(batch)
    batch.last_error = ""
    batch.activity = [*batch.activity, activity_event(user, "apply", _counts_text(counts))]
    batch.save()
    log_batch(user.pk, batch, f"Applied: {_counts_text(counts)}")


def _counts_text(counts: Counter) -> str:
    order = ("created", "updated", "no_change", "skipped", "not_imported")
    names = {"no_change": "no change", "not_imported": "not imported"}
    return ", ".join(f"{counts.get(key, 0)} {names.get(key, key)}" for key in order)


def _send_back(batch_id, fresh, changed: list[int], user) -> None:
    """Store the fresh analysis of the changed rows, reset them to Skip, and flag them for the review.

    Skip, not the row's default: a changed row is applied only after someone has looked at it again.
    """
    by_number = {analysis.row_number: analysis for analysis in fresh}
    with transaction.atomic():
        batch = MemberImportBatch.objects.select_for_update().get(pk=batch_id)
        rows = list(batch.rows.filter(row_number__in=changed))
        for row in rows:
            for name, value in to_stored(by_number[row.row_number]).items():
                setattr(row, name, value)
            row.choice, row.ticks = SKIP, []
            row.changed_since_review = True
            row.chosen_by, row.chosen_at = None, None
            row.updated_at = timezone.now()
        fields = [*to_stored(fresh[0]), "changed_since_review", "chosen_by", "chosen_at", "updated_at"]
        MemberImportRow.objects.bulk_update(rows, fields, batch_size=200)
        batch.choices_version += 1
        numbers = ", ".join(str(number) for number in changed[:20]) + (" …" if len(changed) > 20 else "")
        batch.last_error = (
            f"Nothing was imported: the records of {len(changed)} row(s) changed since you reviewed them (rows "
            f"{numbers}). Their choices were reset; check them and confirm again."
        )
        batch.activity = [*batch.activity, activity_event(user, "stale", batch.last_error)]
        batch.save(update_fields=["choices_version", "last_error", "activity", "updated_at"])


def _note_error(batch_id, message: str, user) -> None:
    with transaction.atomic():
        batch = MemberImportBatch.objects.select_for_update().get(pk=batch_id)
        batch.last_error = f"Nothing was imported. {message}"
        batch.activity = [*batch.activity, activity_event(user, "error", message)]
        batch.save(update_fields=["last_error", "activity", "updated_at"])
