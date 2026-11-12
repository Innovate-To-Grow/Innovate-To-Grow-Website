"""Carry out the planned writes, inside the import's one transaction.

New members are bulk-created (with their addresses and numbers), then one Google Sheet member sync is scheduled after
commit, since ``bulk_create`` skips the save signals. Updates are written one op at a time on the member the apply
locked, so the save signals fire as for any admin edit, and a row that changes nothing writes nothing.
"""

from __future__ import annotations

from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from apps.authn.models import ContactEmail, ContactPhone, Member

from .. import contacts
from .actions import RowPlan

BATCH_SIZE = 500


class RowWriteError(Exception):
    """A row could not be written; the whole import rolls back and the batch goes back to review."""

    def __init__(self, row_number: int, message: str):
        super().__init__(f"Row {row_number}: {message}")
        self.row_number = row_number


def _profile(member, data: dict) -> None:
    for name, value in data.items():
        setattr(member, name, value)
    member.save(update_fields=[*data, "updated_at"])


def _active(member, data: dict) -> None:
    # Member.save also ends an unfinished sign-up when it activates the member.
    member.is_active = data["value"]
    member.save(update_fields=["is_active", "updated_at"])


def _staff(member, data: dict) -> None:
    member.is_staff = data["value"]
    member.save(update_fields=["is_staff", "updated_at"])


_UPDATE_OPS = {
    "profile": lambda member, op: _profile(member, op.data),
    "active": lambda member, op: _active(member, op.data),
    "staff": lambda member, op: _staff(member, op.data),
    "email_flags": lambda member, op: contacts.set_email_flags(member, op.ref, op.data),
    "phone_flags": lambda member, op: contacts.set_phone_flags(member, op.ref, op.data),
    "promote": lambda member, op: contacts.promote_email(member, op.ref),
    "add_email": lambda member, op: contacts.add_email(member, op.data),
    "claim_email": lambda member, op: contacts.claim_email(member, op.ref, op.data),
    "add_phone": lambda member, op: contacts.add_phone(member, op.data),
    "delete_email": lambda member, op: contacts.delete_email(member, op.ref),
    "delete_phone": lambda member, op: contacts.delete_phone(member, op.ref),
}


def execute_update(row_number: int, plan: RowPlan, member: Member) -> None:
    for op in plan.ops:
        try:
            _UPDATE_OPS[op.kind](member, op)
        except contacts.ContactWriteError as exc:
            raise RowWriteError(row_number, str(exc)) from exc


def _new_member(fields: dict, password_hash: str, now) -> Member:
    return Member(
        password=password_hash,
        first_name=fields["first_name"],
        last_name=fields["last_name"],
        middle_name=fields["middle_name"] or None,
        title=fields["title"] or None,
        organization=fields["organization"],
        is_active=fields["is_active"],
        date_joined=fields["date_joined"] or now,
    )


def execute_creations(plans: list[tuple[int, RowPlan]], password_hash: str) -> dict[int, Member]:
    """Create the members of ``(row number, plan)`` pairs; return them by row number."""
    if not plans:
        return {}
    now = timezone.now()
    members = {number: _new_member(plan.ops[0].data, password_hash, now) for number, plan in plans}
    Member.objects.bulk_create(list(members.values()), batch_size=BATCH_SIZE)
    emails, phones, claims = [], [], []
    for number, plan in plans:
        member = members[number]
        for op in plan.ops[1:]:
            if op.kind == "add_email":
                emails.append(
                    ContactEmail(
                        member=member,
                        email_address=op.data["address"],
                        email_type=op.data["type"],
                        verified=op.data["verified"],
                        subscribe=op.data["subscribe"],
                    )
                )
            elif op.kind == "add_phone":
                phones.append(
                    ContactPhone(
                        member=member,
                        phone_number=op.data["number"],
                        region=op.data["region"],
                        # Never from the sheet: only the member's own one-time code verifies a number.
                        verified=False,
                        subscribe=op.data["subscribe"],
                    )
                )
            else:
                claims.append((number, member, op))
    ContactEmail.objects.bulk_create(emails, batch_size=BATCH_SIZE)
    ContactPhone.objects.bulk_create(phones, batch_size=BATCH_SIZE)
    for number, member, op in claims:
        try:
            contacts.claim_email(member, op.ref, op.data)
        except contacts.ContactWriteError as exc:
            raise RowWriteError(number, str(exc)) from exc
    transaction.on_commit(_schedule_sheet_sync, robust=True)
    return members


def _schedule_sheet_sync() -> None:
    from apps.authn.services.members.sheet_sync import schedule_member_sync

    schedule_member_sync()


def log_member_changes(actor_id, entries: list[tuple[Member, bool, str]]) -> None:
    """One history line per member: ``(member, created?, message)``. Shown on the member's History page."""
    if actor_id is None or not entries:
        return
    content_type = ContentType.objects.get_for_model(Member)
    LogEntry.objects.bulk_create(
        [
            LogEntry(
                user_id=actor_id,
                content_type=content_type,
                object_id=str(member.pk),
                object_repr=(member.get_full_name() or str(member.pk))[:200],
                action_flag=ADDITION if created else CHANGE,
                change_message=message,
            )
            for member, created, message in entries
        ],
        batch_size=BATCH_SIZE,
    )


def log_batch(actor_id, batch, message: str) -> None:
    if actor_id is None:
        return
    LogEntry.objects.log_actions(
        user_id=actor_id, queryset=[batch], action_flag=CHANGE, change_message=message, single_object=True
    )
