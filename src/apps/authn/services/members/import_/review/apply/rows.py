"""Writing an import's rows: lock the members it names, then carry out each row's planned writes."""

from __future__ import annotations

from dataclasses import dataclass, field

from apps.authn.models import Member

from ....admins import DEACTIVATE, admin_removal_refusal
from ..analysis.resolution import INVALID
from ..plan.actions import CREATE, CREATE_CLAIM, SKIP
from ..staging.selection import plan_for
from .execute import RowWriteError, execute_creations, execute_update, log_member_changes

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


def lock_members(member_ids) -> dict[str, Member]:
    """Lock the members by primary key, in a fixed order; return them by id."""
    ids = sorted({str(member_id) for member_id in member_ids if member_id})
    query = Member.objects.select_for_update().filter(pk__in=ids).order_by("pk").defer("profile_image", "password")
    return {str(member.pk): member for member in query}


def deactivation_refusal(analyses, selections: dict, snapshot, members: dict, actor) -> str:
    """Why the ticked deactivations may not be applied together (``""`` when they may): the Admin lockout rules
    (never your own Admin account, never the last active Admin), checked on the whole selection against the locked
    members. Each row's tick was already checked on its own by the analysis."""
    targets = []
    for analysis in analyses:
        if analysis.status == INVALID:
            continue
        choice, ticks = selections.get(analysis.row_number, (analysis.default, []))
        plan = plan_for(analysis, choice, ticks, snapshot)
        if any(op.kind == "active" and not op.data["value"] for op in plan.ops) and plan.target in members:
            targets.append(members[plan.target])
    return admin_removal_refusal(actor, targets, action=DEACTIVATE)


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
