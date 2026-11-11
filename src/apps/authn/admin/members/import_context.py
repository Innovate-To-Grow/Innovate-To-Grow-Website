"""What the member import pages show: each row's sheet cells, candidate members, choices and planned changes.

Everything comes from what the batch stored at upload (the rows' values and the records their analysis read), so the
review shows exactly what was analysed; the apply re-reads the records and refuses anything that changed.
"""

from django.urls import NoReverseMatch, reverse

from ...services.members.import_.reader import COLUMN_LABELS
from ...services.members.import_.review import stored_analysis
from ...services.members.import_.review.choices import BULK_CHOICES, BULK_LABELS
from ...services.members.import_.review.describe import PRECEDENCE, conflict_code, conflict_title
from ...services.members.import_.review.lookup import snapshot_from_slice
from ...services.members.import_.review.risky import RISKY_TYPES
from ...services.members.import_.review.selection import plan_for, selection_problems, summarize, tick_items

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
    "phone_verified",
    "phone_subscribed",
    "is_active",
    "is_staff",
)
_PROFILE = ("first_name", "middle_name", "last_name", "organization", "title")
_ROLE_ORDER = {"primary": 0, "secondary": 1, "other": 2}
MATCHED_BY = {"uuid": "Member UUID", "primary": "Primary email", "secondary": "Secondary email", "other": "Other email"}


def _url(name: str, *args) -> str:
    try:
        return reverse(f"admin:{name}", args=args)
    except NoReverseMatch:  # pragma: no cover - every authn admin is registered in this project
        return ""


def member_card(member, *, matched: set[str], matched_by: str = "") -> dict:
    badges = ["Active" if member.is_active else "Inactive"]
    badges += [label for flag, label in ((member.registration_pending, "Unfinished sign-up"),) if flag]
    badges += [label for flag, label in ((member.is_staff, "Staff"), (member.is_superuser, "I2G Master")) if flag]
    emails = sorted(member.emails, key=lambda e: (_ROLE_ORDER.get(e.type, 3), e.address.lower()))
    return {
        "id": member.id,
        "short_id": member.id[:8],
        "name": member.full_name or "Unnamed member",
        "url": _url("authn_member_change", member.id),
        "badges": badges,
        "organization": member.organization,
        "title": member.title,
        "date_joined": member.date_joined[:10],
        "last_login": member.last_login[:10] if member.last_login else "never",
        "matched_by": MATCHED_BY.get(matched_by, ""),
        "emails": [
            {**_contact(e), "address": e.address, "type": e.type, "url": _url("authn_contactemail_change", e.id)}
            | {"matched": e.id in matched}
            for e in emails
        ],
        "phones": [
            {
                **_contact(p),
                "address": p.e164,
                "url": _url("authn_contactphone_change", p.id),
                "matched": p.id in matched,
            }
            for p in member.phones
        ],
    }


def _contact(record) -> dict:
    return {"verified": record.verified, "subscribe": record.subscribe}


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


def _candidates(analysis, snapshot) -> tuple[list[dict], list[dict]]:
    """Member cards for every member the row's analysis read (its target first), and the unlinked records."""
    values, facts = analysis.values, analysis.facts
    records = [
        *snapshot.email_records(values.get("primary_email")),
        *snapshot.email_records(values.get("secondary_email")),
    ]
    matched = {c.id for c in snapshot.email_records(values.get("primary_email"))}
    order = [facts.get("target"), facts.get("uuid_member"), facts.get("email_member"), *snapshot.members]
    cards = []
    for member_id in dict.fromkeys(m for m in order if m):
        member = snapshot.member(member_id)
        if member is not None:
            how = facts.get("matched_by") if member_id == facts.get("target") else ""
            cards.append(member_card(member, matched=matched, matched_by=how))
    unlinked = [
        {"address": c.address, "created": c.created[:10], **_contact(c), "url": _url("authn_contactemail_change", c.id)}
        for c in dict.fromkeys(records)
        if c.member is None
    ]
    return cards, unlinked


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
        "counts": {status: len(items) for status, items in by_status.items()}
        | {"risky": sum(group["count"] for group in risky)},
        "problems": selection_problems(analyses, selections),
        "summary": summarize(analyses, selections),
        "row_numbers": [row.row_number for row in rows],
    }


_STATUSES = ("ready_create", "ready_update", "no_change", "needs_decision", "invalid")

CHOICE_WORDS = {
    "create": "create",
    "update": "update",
    "update_make_primary": "update and make primary",
    "update_same_person": "same person, with the name",
    "update_keep_name": "same person, keep the name",
    "use_member": "use a member",
    "use_row": "use this row",
    "ignore_uuid": "match by email",
    "create_claim": "create a member with the address",
    "attach_to": "attach to a member",
    "skip": "skip",
}
LISTED_TITLES = {
    "emails_deleted": "Contact emails deleted",
    "phones_deleted": "Phone numbers deleted",
    "resubscribed": "Re-subscribed",
    "unverified": "Marked unverified",
    "active_changes": "Members deactivated or reactivated",
    "staff_changes": "Staff changes",
    "primary_changes": "Primary email changes",
}


def confirm_lines(summary: dict) -> dict:
    """The confirm page's decision counts and spelled-out risky changes, in words."""
    decisions = [
        {
            "code": conflict_code(conflict),
            "title": conflict_title(conflict),
            "counts": ", ".join(f"{count} {CHOICE_WORDS.get(choice, choice)}" for choice, count in choices.items()),
        }
        for conflict in PRECEDENCE
        if (choices := summary["decisions"].get(conflict))
    ]
    listed = [
        {"title": title, "items": summary["listed"][kind]}
        for kind, title in LISTED_TITLES.items()
        if summary["listed"].get(kind)
    ]
    return {"decision_lines": decisions, "listed_lines": listed, "rows_summary": summary["rows"]}
