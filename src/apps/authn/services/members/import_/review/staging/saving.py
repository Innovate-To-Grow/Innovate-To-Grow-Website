"""Saving the admin's choices for a staged batch, one row or a bulk control at a time."""

from __future__ import annotations

from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from apps.authn.models import MemberImportBatch, MemberImportRow

from ..analysis.choices import BULK_CHOICES, bulk_value_for
from ..analysis.resolution import NEEDS_DECISION
from ..plan.actions import SKIP
from .batches import Status, activity_event, stored_analysis
from .selection import ForgedSelection, clean_selection, tick_items


@dataclass
class SaveOutcome:
    saved: bool
    message: str = ""
    level: str = "success"
    kept: list[str] = field(default_factory=list)


class StaleVersion(Exception):
    """The posted choices were made on an older version of the review."""


class ReviewClosed(StaleVersion):
    """The batch was applied, discarded or expired after the page was loaded: its choices are final."""


def save_choices(
    batch: MemberImportBatch, *, user, version: int, posted: dict, command: str, bulk: dict
) -> SaveOutcome:
    """Save the posted choices, then run ``command`` (save, a bulk choice, reset, tick all, skip all) on top.

    ``posted`` is ``{row number: (choice or None, [ticks] or None)}`` for the rows the form showed (None keeps what is
    stored); ``bulk`` maps a conflict to the bulk value its control selected. Raises ``ForgedSelection``,
    ``StaleVersion`` or ``ReviewClosed``; nothing is saved then.
    """
    with transaction.atomic():
        locked = MemberImportBatch.objects.select_for_update().get(pk=batch.pk)
        # Checked under the lock: a save that waited for an apply (or a discard) in another request must not rewrite
        # the choices, and who made them, of an import that is already final. The apply does not raise the version.
        if locked.status != Status.REVIEW or locked.expires_at <= timezone.now():
            raise ReviewClosed("This import was already applied, discarded or expired; nothing was saved.")
        if version != locked.choices_version:
            raise StaleVersion(
                "This review was changed in another tab. Its latest choices are shown; check them again."
            )
        rows = list(locked.rows.order_by("row_number"))
        analyses = {row.row_number: stored_analysis(row) for row in rows}
        selections = {}
        for row in rows:
            choice, ticks = posted.get(row.row_number, (None, None))
            selections[row.row_number] = clean_selection(
                analyses[row.row_number], choice or row.choice, row.ticks if ticks is None else ticks
            )
        note = _run_command(command, bulk, analyses, selections)
        changed = _store(rows, selections, user)
        if changed or note:
            locked.choices_version += 1
            if note.detail:
                locked.activity = [*locked.activity, activity_event(user, "bulk", note.detail)]
            locked.save(update_fields=["choices_version", "activity", "updated_at"])
    return SaveOutcome(True, note.message or f"Saved ({changed} row(s) changed).", note.level, note.kept)


@dataclass
class _Note:
    message: str = ""
    detail: str = ""
    level: str = "success"
    kept: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.detail)


def _run_command(command: str, bulk: dict, analyses: dict, selections: dict) -> _Note:
    name, _, arg = command.partition(":")
    if name == "bulk":
        return _bulk_choice(arg, bulk.get(arg, ""), analyses, selections)
    if name == "reset":
        rows = [a for a in analyses.values() if a.conflict == arg]
        for analysis in rows:
            selections[analysis.row_number] = (analysis.default, [])
        return _Note(f"{len(rows)} row(s) reset to Skip.", f"reset {arg}: {len(rows)} rows")
    if name == "skipall":
        rows = [a for a in analyses.values() if a.status == NEEDS_DECISION]
        for analysis in rows:
            selections[analysis.row_number] = (SKIP, [])
        return _Note(f"Every row that needs a decision ({len(rows)}) is set to Skip.", f"skip all: {len(rows)} rows")
    if name == "tickall":
        return _tick_all(arg, analyses, selections)
    return _Note()


def _bulk_choice(conflict: str, value: str, analyses: dict, selections: dict) -> _Note:
    if value not in BULK_CHOICES.get(conflict, ()):
        raise ForgedSelection(f"{value!r} can't be applied to every row of this group")
    rows = [a for a in analyses.values() if a.conflict == conflict]
    if value == "use_first":
        return _use_first(rows, selections)
    applied, kept = 0, []
    for analysis in rows:
        choice = bulk_value_for(value, analysis.options)
        if choice is None:
            reason = next((o["reason"] for o in analysis.options if o["value"].startswith(value) and o["reason"]), "")
            kept.append(f"Row {analysis.row_number}" + (f": {reason}" if reason else ": not offered"))
            continue
        selections[analysis.row_number] = (
            choice,
            [t for t in selections[analysis.row_number][1] if t in _ids(analysis, choice)],
        )
        applied += 1
    message = f"Applied to {applied} row(s)." + (f" {len(kept)} row(s) kept their choice." if kept else "")
    return _Note(
        message, f"bulk {conflict}={value}: {applied} rows, {len(kept)} kept", "warning" if kept else "success", kept
    )


def _ids(analysis, choice: str) -> set[str]:
    return {item["id"] for item in tick_items(analysis, choice)}


def _use_first(rows, selections: dict) -> _Note:
    groups: dict[tuple, list] = {}
    for analysis in rows:
        groups.setdefault(tuple(analysis.facts.get("group", [])), []).append(analysis)
    used, unusable = 0, []
    for group, members in groups.items():
        first = next((a for a in sorted(members, key=lambda a: a.row_number) if "use_row" in _enabled(a)), None)
        for analysis in members:
            selections[analysis.row_number] = ("use_row" if analysis is first else SKIP, [])
        if first is None:
            unusable.append(f"Rows {', '.join(str(n) for n in group)}: no row of the group can be used on its own")
        else:
            used += 1
    message = f"Used the first usable row of {used} group(s)." + (
        f" {len(unusable)} group(s) stay skipped." if unusable else ""
    )
    return _Note(message, f"bulk use first: {used} groups", "warning" if unusable else "success", unusable)


def _enabled(analysis) -> set[str]:
    return {item["value"] for item in analysis.options if item["enabled"]}


def _tick_all(code: str, analyses: dict, selections: dict) -> _Note:
    ticked, disabled = 0, 0
    for number, (choice, ticks) in selections.items():
        for item in tick_items(analyses[number], choice):
            if item["code"] != code or item["id"] in ticks:
                continue
            if item["enabled"]:
                ticks = [*ticks, item["id"]]
                ticked += 1
            else:
                disabled += 1
        selections[number] = (choice, ticks)
    message = f"Ticked {ticked} item(s)." + (f" {disabled} could not be ticked." if disabled else "")
    return _Note(
        message, f"tick all {code}: {ticked} ticked, {disabled} disabled", "warning" if disabled else "success"
    )


def _store(rows, selections: dict, user) -> int:
    now = timezone.now()
    changed = []
    for row in rows:
        choice, ticks = selections[row.row_number]
        if (choice, list(ticks)) != (row.choice, list(row.ticks)):
            row.choice, row.ticks = choice, list(ticks)
            row.chosen_by, row.chosen_at = user, now
            row.changed_since_review = False
            row.updated_at = now
            changed.append(row)
    if changed:
        MemberImportRow.objects.bulk_update(
            changed, ["choice", "ticks", "chosen_by", "chosen_at", "changed_since_review", "updated_at"], batch_size=200
        )
    return len(changed)
