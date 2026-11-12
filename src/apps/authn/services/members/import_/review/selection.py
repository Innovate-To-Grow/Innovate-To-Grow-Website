"""The admin's choices for a batch: what a row's choice plans, what was posted, and what blocks the apply.

A posted choice must be one of the row's enabled options, and a posted tick an enabled risky item of the member the
choice updates; anything else is a forged POST and the whole save is refused. Ticks of a member the new choice no
longer updates are dropped. ``selection_problems`` lists what must be fixed before the apply: two rows changing one
member, two rows of a repeat group both used, or ticks that would remove a member's last verified sign-in contact.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from .actions import CREATE, CREATE_CLAIM, SKIP, UPDATE, RowPlan, resolve_action
from .choices import allowed_values
from .lookup import Snapshot, snapshot_from_slice
from .plan import plan_row

INVALID = "invalid"


class ForgedSelection(Exception):
    """A posted choice or tick the row never offered."""


def plan_for(analysis, choice: str, ticks, snapshot: Snapshot | None = None) -> RowPlan:
    """What ``choice`` (with ``ticks``) writes for ``analysis``'s row, from ``snapshot`` or the row's stored slice."""
    snapshot = snapshot if snapshot is not None else snapshot_from_slice(analysis.slice)
    action = resolve_action(choice, analysis.facts)
    return plan_row(analysis.values, action, snapshot, ticks=ticks, drops=analysis.drops)


def tick_items(analysis, choice: str) -> list[dict]:
    """The risky items of the member ``choice`` updates (none when it creates or skips)."""
    action = resolve_action(choice, analysis.facts)
    if action.kind != UPDATE or not action.target:
        return []
    return analysis.risky.get(action.target, [])


def clean_selection(analysis, choice: str, ticks) -> tuple[str, list[str]]:
    """Check one row's posted choice and ticks; raise ``ForgedSelection`` for anything it never offered."""
    if analysis.status == INVALID:
        return SKIP, []
    choice = choice or analysis.default
    if choice not in allowed_values(analysis.options):
        raise ForgedSelection(f"Row {analysis.row_number}: {choice!r} is not one of this row's choices")
    items = {item["id"]: item for item in tick_items(analysis, choice)}
    known = {item["id"] for items_ in analysis.risky.values() for item in items_}
    kept = []
    for tick in dict.fromkeys(ticks):
        if tick not in known:
            raise ForgedSelection(f"Row {analysis.row_number}: {tick!r} is not one of this row's risky changes")
        if tick in items:
            if not items[tick]["enabled"]:
                raise ForgedSelection(f"Row {analysis.row_number}: {items[tick]['label']} can't be ticked")
            kept.append(tick)
    return choice, kept


def _member_label(analysis, member_id: str) -> str:
    member = snapshot_from_slice(analysis.slice).member(member_id)
    return member.label if member else f"member {member_id}"


def selection_problems(analyses, selections: dict, snapshot: Snapshot | None = None) -> list[str]:
    """What blocks applying ``selections`` (``{row number: (choice, ticks)}``), as sentences."""
    problems: list[str] = []
    claimed: dict[tuple, list[int]] = defaultdict(list)
    labels: dict[tuple, str] = {}
    used: dict[tuple, list[int]] = defaultdict(list)
    for analysis in analyses:
        if analysis.status == INVALID:
            continue
        number = analysis.row_number
        choice, ticks = selections.get(number, (analysis.default, []))
        action = resolve_action(choice, analysis.facts)
        if action.kind == UPDATE:
            key = ("member", action.target)
            claimed[key].append(number)
            labels[key] = _member_label(analysis, action.target)
        if action.claim:
            key = ("claim", action.claim)
            claimed[key].append(number)
            labels[key] = f"the contact email {analysis.values.get('primary_email')}"
        if choice == "use_row":
            used[tuple(analysis.facts.get("group", []))].append(number)
        plan = plan_for(analysis, choice, ticks, snapshot)
        problems.extend(f"Row {number}: {problem}" for problem in plan.problems)
    for key, rows in claimed.items():
        if len(rows) > 1:
            problems.append(
                f"Rows {_rows(rows)} would all change {labels[key]}. Choose one of them and skip the others."
            )
    for group, rows in used.items():
        if len(rows) > 1:
            problems.append(f"Rows {_rows(rows)} are the same person; use only one of them (rows {_rows(group)}).")
    return problems


def _rows(numbers) -> str:
    numbers = [str(number) for number in numbers]
    return ", ".join(numbers[:-1]) + f" and {numbers[-1]}" if len(numbers) > 1 else "".join(numbers)


def summarize(analyses, selections: dict, snapshot: Snapshot | None = None) -> dict:
    """Counts for the confirm page: rows by what they will do, decisions per conflict and choice, and the spelled-out
    risky changes (deleted contacts, re-subscriptions, primary changes, …)."""
    rows: Counter = Counter()
    decisions: dict[str, Counter] = defaultdict(Counter)
    listed: dict[str, list[str]] = defaultdict(list)
    for analysis in analyses:
        if analysis.status == INVALID:
            rows["not_imported"] += 1
            continue
        choice, ticks = selections.get(analysis.row_number, (analysis.default, []))
        plan = plan_for(analysis, choice, ticks, snapshot)
        if analysis.conflict:
            decisions[analysis.conflict][choice.split(":")[0]] += 1
        rows[_row_outcome(plan)] += 1
        for kind, items in plan.listed.items():
            listed[kind].extend(f"Row {analysis.row_number}: {item}" for item in items)
    return {"rows": dict(rows), "decisions": {k: dict(v) for k, v in decisions.items()}, "listed": dict(listed)}


def _row_outcome(plan: RowPlan) -> str:
    if plan.kind == SKIP:
        return "skipped"
    if plan.kind in (CREATE, CREATE_CLAIM):
        return "created"
    return "updated" if plan.writes else "no_change"
