"""Work out what each row of a sheet would do, without writing anything.

A row resolves in this order: its Member UUID (when the sheet has one), then its Primary Email cell, looked up in every
role (a member's primary, secondary or "other" address, or a contact email with no member), then a new member. Each
row ends as ``invalid`` (cannot import), ``needs_decision`` (one conflict, C1–C9, shown in the precedence of
``describe.PRECEDENCE``), ``ready_create``, ``ready_update`` or ``no_change``. A row that needs a decision is skipped
until an admin chooses otherwise. The review is the plan: the apply re-runs this analysis on freshly read records and
applies nothing if any row's records changed (``fingerprint``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..lookup.load import row_slice
from ..lookup.records import Snapshot, fingerprint
from ..plan.actions import SKIP, UPDATE, resolve_action
from ..plan.rows import apply_drops, plan_row
from .choices import OptionContext, ready_options
from .conflict_choices import options_for
from .describe import describe_action, why
from .grouping import cross_row_drops, duplicate_groups
from .resolution import (
    INVALID,
    NEEDS_DECISION,
    NO_CHANGE,
    READY_UPDATE,
    UPDATE_EXISTING,
    Context,
    Resolution,
    _attach_candidates,
    resolve_row,
    suggested_action,
)
from .risky import risky_items

_BEFORE_C1 = frozenset({"privileged_target", "ambiguous_address", "uuid_email_mismatch", "uuid_not_found"})


@dataclass
class RowAnalysis:
    values: dict
    status: str
    conflict: str = ""
    facts: dict = field(default_factory=dict)
    options: list[dict] = field(default_factory=list)
    default: str = SKIP
    warnings: list[dict] = field(default_factory=list)
    risky: dict = field(default_factory=dict)
    slice: dict = field(default_factory=dict)
    fingerprint: str = ""

    @property
    def row_number(self) -> int:
        return self.values["row"]

    @property
    def target(self) -> str | None:
        return self.facts.get("target")

    @property
    def drops(self) -> dict:
        return self.facts.get("drops", {})


def analyse_rows(rows: list[dict], snapshot: Snapshot, ctx: Context) -> list[RowAnalysis]:
    """Analyse parsed ``rows`` against ``snapshot`` (``lookup.load_snapshot(rows)``)."""
    # Resolving reads no Secondary Email or Phone Number cell, so it comes first: a row that can't be imported then
    # never takes a cell another row could add (V8).
    resolutions = [resolve_row(row, snapshot, ctx) for row in rows]
    invalid = {row["row"] for row, resolution in zip(rows, resolutions, strict=True) if resolution.status == INVALID}
    drops = cross_row_drops(rows, snapshot, invalid)
    groups = duplicate_groups(rows, resolutions)
    return [
        _finish(row, resolution, snapshot, ctx, drops=drops.get(row["row"], {}), group=groups.get(row["row"], []))
        for row, resolution in zip(rows, resolutions, strict=True)
    ]


def _finish(values, resolution: Resolution, snapshot: Snapshot, ctx: Context, *, drops: dict, group: list[int]):
    facts = {
        "target": resolution.target,
        "matched_by": resolution.matched_by,
        "record": resolution.record,
        "uuid_member": resolution.uuid_member,
        "email_member": resolution.email_member,
        "drops": drops,
        "group": group,
        "invalid": resolution.invalid,
    }
    analysis = RowAnalysis(values=values, status=resolution.status, facts=facts)
    analysis.warnings = [*values.get("warnings", []), *drops.values()]
    if resolution.status == INVALID:
        return _seal(analysis, snapshot)
    conflict = "duplicate_in_sheet" if group and resolution.conflict not in _BEFORE_C1 else resolution.conflict
    dropped = apply_drops(values, drops)
    oc = OptionContext(snapshot, ctx, dropped)
    if conflict:
        _decision(analysis, conflict, resolution, oc, ctx)
    else:
        target = snapshot.member(resolution.target)
        analysis.options = ready_options(resolution.status, target.label if target else "")
        analysis.default = analysis.options[0]["value"]
        if (
            resolution.status == READY_UPDATE
            and not plan_row(values, resolve_action("update", facts), snapshot, drops=drops).writes
        ):
            analysis.status = NO_CHANGE
    analysis.risky = _risky(analysis, dropped, snapshot, ctx)
    return _seal(analysis, snapshot)


def _decision(analysis: RowAnalysis, conflict: str, resolution: Resolution, oc: OptionContext, ctx: Context) -> None:
    analysis.status, analysis.conflict = NEEDS_DECISION, conflict
    facts, values, snapshot = analysis.facts, oc.values, oc.snapshot
    if conflict == "exists_but_skip_mode" and ctx.mode == UPDATE_EXISTING and not ctx.can_update:
        facts["no_permission"] = True
    if conflict == "duplicate_in_sheet":
        solo, reason = suggested_action(resolution, values, ctx)
        facts.update(solo=solo.as_dict() if solo else None, solo_reason=reason)
        facts["solo_text"] = describe_action(solo, snapshot, values) if solo else ""
    if conflict == "uuid_not_found":
        fallback_resolution = resolve_row(values, snapshot, ctx, use_uuid=False)
        fallback, reason = suggested_action(fallback_resolution, values, ctx)
        if fallback_resolution.status == INVALID:
            fallback, reason = None, fallback_resolution.invalid
        facts.update(fallback=fallback.as_dict() if fallback else None, fallback_reason=reason)
        facts["fallback_text"] = describe_action(fallback, snapshot, values) if fallback else ""
    if conflict == "unlinked_address":
        facts["attach_candidates"] = _attach_candidates(values, snapshot, resolution)
    analysis.options = options_for(conflict, facts, oc)
    analysis.default = SKIP
    facts["why"] = why(conflict, values, snapshot, **facts)


def update_targets(analysis: RowAnalysis) -> list[str]:
    """Each member one of the row's options would update."""
    targets = []
    for item in analysis.options:
        action = resolve_action(item["value"], analysis.facts)
        if action.kind == UPDATE and action.target and action.target not in targets:
            targets.append(action.target)
    return targets


def _risky(analysis: RowAnalysis, dropped: dict, snapshot: Snapshot, ctx: Context) -> dict:
    items = {}
    for target in update_targets(analysis):
        member = snapshot.member(target)
        owned = [c.id for c in snapshot.email_records(dropped.get("primary_email")) if c.member == target]
        found = risky_items(dropped, member, snapshot, matched=owned[0] if owned else None, is_master=ctx.is_master)
        if found:
            items[target] = found
    return items


def _seal(analysis: RowAnalysis, snapshot: Snapshot) -> RowAnalysis:
    analysis.slice = row_slice(snapshot, analysis.values)
    analysis.fingerprint = fingerprint(analysis.slice)
    return analysis
