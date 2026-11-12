"""Switching a member's primary email to another of their verified addresses, and recording what changed.

``make_contact_email_primary`` (``contact_emails``) stays the one place a primary changes: it locks the member row
(the mutex every contact-email write takes), requires a verified target, and moves the old primary to ``secondary``
and the previous secondary to ``other``, in the order the one-primary-per-member index needs. The admin's **Switch
primary email** (member page) and **Make selected email primary** (Contact Emails) call it through
``switch_primary_email``, which runs in the same transaction and also:

* refuses, with a message staff can act on, an address that is not the member's or not verified;
* refuses when the member or their addresses changed after the confirmation page was shown (``fingerprint``);
* reads back every address whose type changed (``PrimarySwitch.changes``), for the admin history (``log_switch``).

``plan_primary_switch`` predicts those changes for the confirmation page without writing anything; it mirrors the
service, and the tests hold the two together. A switch never changes a subscription or a verification, and sends
nothing to any address.
"""

import hashlib
import json
import logging
from dataclasses import dataclass

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.db import transaction

from apps.authn.models import ContactEmail
from apps.authn.services.contacts.contact_emails import make_contact_email_primary
from apps.authn.services.email.challenges import AuthChallengeError

logger = logging.getLogger(__name__)

PRIMARY, SECONDARY, OTHER = "primary", "secondary", "other"
ROLE_WORDS = {PRIMARY: "the primary", SECONDARY: "the secondary", OTHER: "other"}

NOT_FOUND = "That address is not one of this member's email addresses any more. Pick one of the addresses listed."
NOT_VERIFIED = (
    "{address} is not verified, so it cannot become the primary: only a verified address can be used to sign in. "
    "Ask the member to verify it from their account page (or mark it verified in Contact Emails if you are sure it is "
    "theirs), then switch."
)
STALE = (
    "This member or their email addresses changed after the page was shown, so nothing was changed. Check the "
    "addresses below and confirm again."
)


class SwitchRefused(Exception):
    """The switch was not applied and nothing changed; the message says why."""


class StaleSwitch(SwitchRefused):
    """The member or their addresses changed after the confirmation page was shown."""


@dataclass(frozen=True)
class RoleChange:
    """One address whose type changes (``before`` → ``after``)."""

    contact: ContactEmail
    before: str
    after: str


@dataclass(frozen=True)
class PrimarySwitch:
    """What a switch did: the new primary, the primary before it (None: the member had none) and every type change."""

    member: object
    primary: ContactEmail
    previous: ContactEmail | None
    changes: tuple[RoleChange, ...]

    @property
    def changed(self) -> bool:
        return bool(self.changes)


def member_emails(member) -> list[ContactEmail]:
    """The member's contact emails, oldest first."""
    return list(ContactEmail.objects.filter(member=member).order_by("created_at", "pk"))


def current_primary(emails) -> ContactEmail | None:
    """The primary among ``emails`` (the oldest one, as ``make_contact_email_primary`` picks it)."""
    primaries = [email for email in emails if email.email_type == PRIMARY]
    return min(primaries, key=lambda email: email.created_at) if primaries else None


def fingerprint(member, emails) -> str:
    """A digest of everything the confirmation page showed and the guards read."""
    parts = [
        str(member.pk),
        member.is_active,
        member.is_staff,
        member.is_superuser,
        [(str(e.pk), e.email_address, e.email_type, e.verified, e.subscribe) for e in emails],
    ]
    return hashlib.sha256(json.dumps(parts).encode("utf-8")).hexdigest()[:40]


def plan_primary_switch(emails, target) -> list[RoleChange]:
    """The type changes ``make_contact_email_primary`` makes when ``target`` becomes the primary (nothing is saved)."""
    if target.email_type == PRIMARY:
        return []
    changes = []
    previous = current_primary(emails)
    if previous is not None:
        secondaries = [email for email in emails if email.email_type == SECONDARY and email.pk != target.pk]
        if secondaries:
            # ContactEmail is ordered newest first, so the service's ``.first()`` moves the newest secondary aside.
            changes.append(RoleChange(max(secondaries, key=lambda email: email.created_at), SECONDARY, OTHER))
        changes.append(RoleChange(previous, PRIMARY, SECONDARY))
    changes.append(RoleChange(target, target.email_type, PRIMARY))
    return changes


@transaction.atomic
def switch_primary_email(*, member, contact_email_id, seen: str | None = None) -> PrimarySwitch:
    """Make the member's verified address ``contact_email_id`` their primary email.

    ``seen`` is the ``fingerprint`` the confirmation page showed: when given, the switch is refused (``StaleSwitch``)
    if anything changed since. Raises ``SwitchRefused`` for an address that is not the member's or is not verified.
    """
    locked = get_user_model().objects.select_for_update().get(pk=member.pk)
    before = member_emails(locked)
    if seen is not None and fingerprint(locked, before) != seen:
        raise StaleSwitch(STALE)
    target = next((email for email in before if str(email.pk) == str(contact_email_id)), None)
    if target is None:
        raise SwitchRefused(NOT_FOUND)
    if target.email_type != PRIMARY and not target.verified:
        raise SwitchRefused(NOT_VERIFIED.format(address=target.email_address))
    try:
        make_contact_email_primary(member=locked, contact_email_id=target.pk)
    except AuthChallengeError as exc:  # pragma: no cover - the checks above ran under the same member lock
        raise SwitchRefused(str(exc)) from exc
    after = {email.pk: email for email in member_emails(locked)}
    changes = tuple(
        RoleChange(after[email.pk], email.email_type, after[email.pk].email_type)
        for email in before
        if email.pk in after and after[email.pk].email_type != email.email_type
    )
    return PrimarySwitch(member=locked, primary=after[target.pk], previous=current_primary(before), changes=changes)


def describe(result: PrimarySwitch) -> str:
    """One sentence for the member's history, for example: Primary email switched from old@example.org to
    new@example.org: old@example.org is now the secondary."""
    new = result.primary.email_address
    if result.previous is None:
        head = f"Primary email set to {new} (the member had none)"
    else:
        head = f"Primary email switched from {result.previous.email_address} to {new}"
    moved = [
        f"{change.contact.email_address} is now {ROLE_WORDS.get(change.after, change.after)}"
        for change in result.changes
        if change.contact.pk != result.primary.pk
    ]
    return f"{head}: {'; '.join(moved)}." if moved else f"{head}."


def log_switch(actor, result: PrimarySwitch, *, via: str) -> None:
    """Write the switch to the admin history: one line on the member and one on each address whose type changed."""
    if not result.changed:
        return
    summary = f"{describe(result)} ({via})"
    LogEntry.objects.log_actions(
        user_id=actor.pk, queryset=[result.member], action_flag=CHANGE, change_message=summary, single_object=True
    )
    for change in result.changes:
        LogEntry.objects.log_actions(
            user_id=actor.pk,
            queryset=[change.contact],
            action_flag=CHANGE,
            change_message=f"Email type changed from {change.before} to {change.after}. {summary}",
            single_object=True,
        )
    # Ids only: addresses stay out of the application log.
    logger.info(
        "Admin %s switched the primary email of member %s from contact %s to contact %s",
        actor.pk,
        result.member.pk,
        result.previous.pk if result.previous is not None else None,
        result.primary.pk,
    )
