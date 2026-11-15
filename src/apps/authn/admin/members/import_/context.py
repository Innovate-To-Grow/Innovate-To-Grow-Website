"""What the member import pages show: each row's sheet cells, candidate members, choices and planned changes.

Everything comes from what the batch stored at upload (the rows' values and the records their analysis read), so the
review shows exactly what was analysed; the apply re-reads the records and refuses anything that changed.
"""

from ....services.members.import_.reader import COLUMN_LABELS
from ....services.members.import_.review import stored_analysis
from ....services.members.import_.review.analysis.choices import BULK_CHOICES, BULK_LABELS
from ....services.members.import_.review.analysis.describe import PRECEDENCE, conflict_code, conflict_title
from ....services.members.import_.review.analysis.risky import RISKY_TYPES
from ....services.members.import_.review.lookup import snapshot_from_slice
from ....services.members.import_.review.staging.selection import plan_for, selection_problems, summarize, tick_items
from .member_cards import _candidates, _url

CELL_ORDER = (
    "member_uuid",
    "first_name",
    "middle_name",
    "last_name",
    "organization",
    "title",
    "when_started",
    "primary_email",
    "primary_verified",
    "primary_subscribed",
    "secondary_email",
    "secondary_verified",
    "secondary_subscribed",
    "phone_number",
    "phone_subscribed",
    "is_active",
    "is_staff",
)
_PROFILE = ("first_name", "middle_name", "last_name", "organization", "title")


def _cells(values: dict, keys: list[str], target) -> list[dict]:
    raw = values.get("raw") or {}
    cells = []
    for key in CELL_ORDER:
        if key not in keys:
            continue
        text = raw.get(key, "")
        differs = bool(target is not None and key in _PROFILE and text and text != getattr(target, key, ""))
        cells.append({"label": COLUMN_LABELS.get(key, key), "text": text, "blank": not text, "differs": differs})
    return cells


def row_view(row, analysis, keys: list[str]) -> dict:
    snapshot = snapshot_from_slice(analysis.slice)
    target = snapshot.member(analysis.target)
    plan = plan_for(analysis, row.choice, row.ticks, snapshot)
    members, unlinked = _candidates(analysis, snapshot)
    return {
        "row": row,
        "number": row.row_number,
        "code": conflict_code(row.conflict),
        "title": conflict_title(row.conflict),
        "why": analysis.facts.get("why", ""),
        "invalid": analysis.facts.get("invalid", ""),
        "cells": _cells(analysis.values, keys, target),
        "members": members,
        "unlinked": unlinked,
        "target_url": _url("authn_member_change", target.id) if target else "",
        "target_name": target.full_name if target else "",
        "options": [{**item, "checked": item["value"] == row.choice} for item in analysis.options],
        "default": analysis.default,
        "skip_checked": row.choice == "skip",
        "plan": plan,
        "ticks": [{**item, "checked": item["id"] in row.ticks} for item in tick_items(analysis, row.choice)],
        "tick_groups": _tick_groups(analysis, row, snapshot),
        "warnings": analysis.warnings,
    }


def _tick_groups(analysis, row, snapshot) -> list[dict]:
    """A decision row's risky ticks for each member it could update; only the chosen member's ticks apply."""
    groups = []
    for member_id, items in analysis.risky.items():
        member = snapshot.member(member_id)
        groups.append(
            {
                "member": member.label if member else member_id,
                "items": [{**item, "checked": item["id"] in row.ticks} for item in items],
            }
        )
    return groups


def _risky_groups(views: list[dict]) -> list[dict]:
    """The ticks of rows that don't need a decision, by type (a decision row's ticks are on its card)."""
    groups = {code: {"code": code, "title": title, "items": [], "count": 0} for code, title in RISKY_TYPES.items()}
    for view in views:
        for item in view["ticks"]:
            group = groups[item["code"]]
            group["count"] += item["enabled"]
            if view["row"].status != "needs_decision":
                group["items"].append({"view": view, "item": item})
    return [group for group in groups.values() if group["items"] or group["count"]]


def review_sections(batch) -> dict:
    """The review page's sections and counts."""
    rows = list(batch.rows.order_by("row_number").select_related("chosen_by"))
    analyses = [stored_analysis(row) for row in rows]
    keys = (batch.columns or {}).get("keys", [])
    views = [row_view(row, analysis, keys) for row, analysis in zip(rows, analyses, strict=True)]
    by_status = {status: [v for v in views if v["row"].status == status] for status in _STATUSES}
    decisions = []
    for conflict in PRECEDENCE:
        group_views = [v for v in by_status["needs_decision"] if v["row"].conflict == conflict]
        if group_views:
            decisions.append(
                {
                    "conflict": conflict,
                    "code": conflict_code(conflict),
                    "title": conflict_title(conflict),
                    "views": group_views,
                    "bulk": [(value, BULK_LABELS[value]) for value in BULK_CHOICES[conflict]],
                }
            )
    risky = _risky_groups(views)
    selections = {row.row_number: (row.choice, row.ticks) for row in rows}
    return {
        "decisions": decisions,
        "risky": risky,
        "invalid": by_status["invalid"],
        "ready": by_status["ready_create"] + by_status["ready_update"],
        "no_change": by_status["no_change"],
        "no_change_changed": any(view["row"].changed_since_review for view in by_status["no_change"]),
        "ready_changed": any(
            view["row"].changed_since_review for view in by_status["ready_create"] + by_status["ready_update"]
        ),
        "counts": {status: len(items) for status, items in by_status.items()}
        | {"risky": sum(group["count"] for group in risky)},
        "problems": selection_problems(analyses, selections),
        "summary": summarize(analyses, selections),
        "row_numbers": [row.row_number for row in rows],
    }


_STATUSES = ("ready_create", "ready_update", "no_change", "needs_decision", "invalid")
