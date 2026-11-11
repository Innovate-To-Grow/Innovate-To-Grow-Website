"""Apply a reviewed import: every row in one transaction, all or nothing.

The batch row is locked first, so a double click, a second tab or a browser resubmit waits and then finds the batch
applied. The members the review read are locked in primary-key order (the self-service contact services lock the
member row too, so a member editing their addresses waits instead of racing). Then every row is analysed again from
freshly read records. If any row's records changed since the review (its fingerprint differs), or a choice is no longer
allowed, nothing is applied: those rows go back to review with their choices reset. A row that fails to write rolls
everything back, and the batch stays in review with the reason in ``last_error``.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils import timezone

from apps.authn.models import Member, MemberImportBatch, MemberImportRow

from ..parsing import generate_random_password, values_from_json
from .actions import CREATE, CREATE_CLAIM, SKIP
from .analysis import INVALID, Context, analyse_rows
from .batches import activity_event, forget_password, to_stored
from .choices import allowed_values
from .execute import RowWriteError, execute_creations, execute_update, log_batch, log_member_changes
from .lookup import load_snapshot
from .selection import plan_for, selection_problems, tick_items

MATCHED_BY = {
    "uuid": "matched by Member UUID",
    "primary": "matched by primary email",
    "secondary": "matched by secondary email",
    "other": 'matched by an "other" email',
}


@dataclass
class RowOutcome:
    row_number: int
    outcome: str
    changes: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    member: Member | None = None
    reason: str = ""
    listed: dict = field(default_factory=dict)


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


def lock_members(member_ids) -> dict[str, Member]:
    """Lock the members by primary key, in a fixed order; return them by id."""
    ids = sorted({str(member_id) for member_id in member_ids if member_id})
    query = Member.objects.select_for_update().filter(pk__in=ids).order_by("pk").defer("profile_image", "password")
    return {str(member.pk): member for member in query}


def run_import(analyses, selections: dict, snapshot, *, password_hash: str, members: dict, actor_id=None, label=""):
    """Write every row's chosen plan (inside the caller's transaction) and return one ``RowOutcome`` per row."""
    outcomes: dict[int, RowOutcome] = {}
    planned = []
    for analysis in analyses:
        number = analysis.row_number
        if analysis.status == INVALID:
            outcomes[number] = RowOutcome(number, "not_imported", reason=analysis.facts.get("invalid", ""))
            continue
        choice, ticks = selections.get(number, (analysis.default, []))
        plan = plan_for(analysis, choice, ticks, snapshot)
        if plan.problems:
            raise RowWriteError(number, plan.problems[0])
        planned.append((analysis, plan))
    created = execute_creations(
        [(a.row_number, plan) for a, plan in planned if plan.kind in (CREATE, CREATE_CLAIM)], password_hash
    )
    history = []
    for analysis, plan in planned:
        outcome = _write_row(analysis, plan, created, members, getattr(snapshot, "objects", {}))
        outcomes[outcome.row_number] = outcome
        if outcome.outcome == "created":
            history.append((outcome.member, True, f"Created by member import {label}, row {outcome.row_number}"))
        elif outcome.outcome == "updated":
            how = MATCHED_BY.get(analysis.facts.get("matched_by"), "")
            prefix = f"Member import {label}, row {outcome.row_number}: " + (f"{how}; " if how else "")
            history.append((outcome.member, False, prefix + "; ".join(plan.changes)))
    log_member_changes(actor_id, history)
    return [outcomes[analysis.row_number] for analysis in analyses]


def _write_row(analysis, plan, created: dict, members: dict, known: dict) -> RowOutcome:
    number = analysis.row_number
    listed = {kind: list(items) for kind, items in plan.listed.items()}
    if plan.kind == SKIP:
        member = members.get(analysis.target) or known.get(analysis.target)
        return RowOutcome(number, "skipped", member=member, reason=analysis.facts.get("why", ""))
    if plan.kind in (CREATE, CREATE_CLAIM):
        return RowOutcome(number, "created", plan.changes, plan.notes, created[number], listed=listed)
    member = members.get(plan.target)
    if member is None:
        raise RowWriteError(number, "the member the review showed no longer exists")
    if not plan.writes:
        return RowOutcome(number, "no_change", notes=plan.notes, member=member)
    execute_update(number, plan, member)
    return RowOutcome(number, "updated", plan.changes, plan.notes, member, listed=listed)


def changed_rows(stored_rows, fresh) -> list[int]:
    """Rows whose records changed since the review, or whose choice or ticks are no longer allowed."""
    changed = []
    for row, analysis in zip(stored_rows, fresh, strict=True):
        enabled = {item["id"] for item in tick_items(analysis, row.choice) if item["enabled"]}
        if (
            row.fingerprint != analysis.fingerprint
            or (row.status, row.conflict) != (analysis.status, analysis.conflict)
            or (analysis.status != INVALID and row.choice not in allowed_values(analysis.options))
            or not set(row.ticks) <= enabled
        ):
            changed.append(row.row_number)
    return changed


def apply_batch(batch_id, *, user, version: int, ctx: Context) -> ApplyResult:
    """Apply a batch for ``user`` (who may change it: the view checks). See the module docstring."""
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
    problems = selection_problems(fresh, selections, snapshot)
    if problems:
        return ApplyResult("refused", problems[0])
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
