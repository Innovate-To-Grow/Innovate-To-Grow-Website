"""The member import without a review, for scripts and tests.

It runs the review's analysis and applies what a review would apply if nobody changed a thing: ready rows are created
or updated, every row that needs a decision (C1–C9) is skipped with the reason, and no risky change (R1–R8) is made.
So it never deletes, re-subscribes or un-verifies a contact, never changes Active or Staff, never moves a contact
between members, and never changes a primary email. It never verifies a phone number either: a Phone Verified column
is ignored and reported once, before the rows. Everything is written in one transaction: a row that fails to write
rolls the whole import back. The admin's Members → Import page uses the review flow (``review/``) instead.
"""

from __future__ import annotations

from collections.abc import Callable

from django.contrib.auth.hashers import make_password
from django.db import transaction

from apps.authn.models import Member

from .parsing import generate_random_password
from .reader import read_upload
from .review.analysis import INVALID, NEEDS_DECISION, SKIP_EXISTING, UPDATE_EXISTING, Context, analyse_rows
from .review.apply import lock_members, run_import
from .review.describe import conflict_code, conflict_title
from .review.lookup import load_snapshot
from .types import ImportResult


def import_members_from_excel(
    file,
    default_password: str | None = None,
    update_existing: bool = False,
    update_member_allowed: Callable[[Member], bool] | None = None,
    allow_privilege_fields: bool = False,
) -> ImportResult:
    """Import ``file`` without a review. With ``update_existing``, rows matching a member by primary email (or by
    Member UUID) update that member; ``update_member_allowed`` may refuse a member (the row is then skipped). Without
    it, staff and superuser accounts are skipped unless ``allow_privilege_fields`` (the caller is an I2G Master)."""
    read = read_upload(file)
    if read.error:
        return ImportResult(success=False, errors=[read.error])
    ctx = Context(
        mode=UPDATE_EXISTING if update_existing else SKIP_EXISTING,
        is_master=allow_privilege_fields,
        can_update=update_existing,
        can_manage=update_member_allowed or (lambda member: _ordinary_or_master(member, allow_privilege_fields)),
    )
    try:
        with transaction.atomic():
            first = analyse_rows(read.rows, load_snapshot(read.rows), ctx)
            members = lock_members(a.target for a in first if a.status not in (INVALID, NEEDS_DECISION))
            snapshot = load_snapshot(read.rows)
            analyses = analyse_rows(read.rows, snapshot, ctx)
            password_hash = make_password(default_password or generate_random_password())
            outcomes = run_import(analyses, {}, snapshot, password_hash=password_hash, members=members)
    except Exception as exc:  # noqa: BLE001 - RowWriteError or a database error: either way nothing was written.
        return ImportResult(success=False, errors=[f"Error importing members: {exc}. Nothing was imported"])
    return _result(analyses, outcomes, read.columns.get("notes", []))


def _ordinary_or_master(member, is_master: bool) -> bool:
    """Without a permission check of its own, a caller changes staff and superuser accounts only as an I2G Master."""
    return is_master or not (member.is_staff or member.is_superuser)


def _result(analyses, outcomes, file_notes) -> ImportResult:
    result = ImportResult(success=True)
    for note in file_notes:
        result.note_file(note)
    for analysis, outcome in zip(analyses, outcomes, strict=True):
        number, member = analysis.row_number, outcome.member
        if outcome.outcome == "not_imported":
            result.skip_row(number, outcome.reason)
        elif outcome.outcome == "skipped":
            code, title = conflict_code(analysis.conflict), conflict_title(analysis.conflict)
            result.skip_row(number, f"needs a decision ({code}: {title}). {outcome.reason}", member)
        else:
            if outcome.outcome == "created":
                result.created_count += 1
            else:
                result.updated_count += 1
                result.unchanged_count += outcome.outcome == "no_change"
            for warning in analysis.warnings:
                result.note_row(number, warning["text"], member)
            for note in outcome.notes:
                result.note_row(number, note, member)
            result.details.append(
                {
                    "row": number,
                    "member_id": str(member.pk) if member else None,
                    "outcome": outcome.outcome,
                    "changes": outcome.changes,
                }
            )
    result.sort_by_row()
    return result
