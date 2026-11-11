"""Stage an upload as a batch, and keep the admin's choices for it until it is applied or discarded.

Creating a batch writes only the batch and its rows: no member data. Every save of choices carries the batch's
``choices_version`` and raises it, so a page loaded before another tab's save can neither overwrite those choices nor
be confirmed. Each changed row records who chose and when; bulk controls are also kept in the batch's activity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils import timezone

from apps.authn.models import MemberImportBatch, MemberImportRow

from ..parsing import values_from_json, values_to_json
from .actions import SKIP
from .analysis import NEEDS_DECISION, Context, RowAnalysis, analyse_rows
from .choices import BULK_CHOICES, bulk_value_for
from .lookup import load_snapshot
from .selection import ForgedSelection, clean_selection, tick_items

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
    """An expired review keeps no password hash and can't be applied; the purge deletes it."""
    if batch.status == Status.REVIEW and batch.expires_at <= timezone.now():
        batch.status = Status.EXPIRED
        forget_password(batch)
        batch.save(update_fields=["status", "default_password_hash", "updated_at"])


def discard_batch(batch: MemberImportBatch, user) -> None:
    with transaction.atomic():
        locked = MemberImportBatch.objects.select_for_update().get(pk=batch.pk)
        if locked.status != Status.REVIEW:
            return
        locked.status = Status.DISCARDED
        forget_password(locked)
        locked.activity = [*locked.activity, activity_event(user, "discard")]
        locked.save(update_fields=["status", "default_password_hash", "activity", "updated_at"])


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
