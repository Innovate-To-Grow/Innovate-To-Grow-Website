"""Lockout rules for Admin accounts.

Every Admin has the same, complete permissions, so nothing ranks one Admin above another. Two rules keep the site
from being locked out, whatever path removes an Admin (the member form and its bulk actions, a delete, the member
import, Email Monitoring, the AI assistant, the public account page):

- nobody deletes, deactivates or removes Admin access from **their own** Admin account (another Admin must do it);
- the **last active Admin** is never deleted, deactivated or demoted.

An Admin here is an active member with ``is_staff``; removing a regular member, or an Admin account that is already
inactive, is never refused by these rules.
"""

from collections.abc import Iterable

from django.db import transaction

DELETE = "delete"
DEACTIVATE = "deactivate"
DEMOTE = "demote"

_VERBS = {
    DELETE: "delete",
    DEACTIVATE: "deactivate",
    DEMOTE: "remove Admin access from",
}


def _member_model():
    from apps.authn.models import Member

    return Member


def admin_removal_refusal(actor, targets: Iterable, *, action: str) -> str:
    """Why ``actor`` may not ``action`` ``targets`` ("" when the rules allow it).

    ``targets`` are the members about to be deleted, deactivated or demoted (an iterable or a queryset); ``actor`` is
    the member doing it (``None`` for a system path, which only the last-Admin rule applies to). Inside a transaction
    the remaining active Admins are locked, so two Admins removing each other at the same moment cannot both pass.
    """
    if action not in _VERBS:
        raise ValueError(f"Unknown admin removal action: {action!r}")
    affected = {member.pk for member in targets if member.is_staff and member.is_active}
    if not affected:
        return ""
    verb = _VERBS[action]
    actor_pk = getattr(actor, "pk", None)
    if actor_pk is not None and actor_pk in affected:
        return f"You cannot {verb} your own Admin account. Ask another Admin to do it."
    remaining = _member_model().objects.filter(is_staff=True, is_active=True).exclude(pk__in=affected)
    if transaction.get_connection(remaining.db).in_atomic_block:
        remaining = remaining.select_for_update()
    if not remaining.values_list("pk", flat=True)[:1]:
        noun = "this Admin account" if len(affected) == 1 else "these Admin accounts"
        return f"You cannot {verb} {noun}: the site must keep at least one active Admin."
    return ""
