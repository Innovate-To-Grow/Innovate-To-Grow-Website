"""Newsletter opt-out and opt-in behind the emailed one-click unsubscribe and resubscribe links.

``ContactEmail.subscribe`` is a per-address flag and the only source of truth for the "subscribers" audience
(see ``audience.resolvers``). The one-click link unsubscribes the person: every address of the member. The
resubscribe link restores exactly the addresses that unsubscribe turned off.

Both changes lock the member row (the mutex ``authn.services.contacts.contact_emails`` uses for every
contact-email change), then the rows to flip. A concurrent second request therefore sees nothing left to change,
which keeps the endpoints idempotent and sends at most one confirmation per real change (and, see
``tokens.notifications``, at most one per member and action per hour).
"""

from django.db import transaction
from django.utils import timezone

from apps.authn.models import ContactEmail, Member
from apps.authn.signals import schedule_member_sync_on_change

from .tokens.notifications import send_subscription_confirmation


def member_has_subscribed_email(member) -> bool:
    return ContactEmail.objects.filter(member=member, subscribe=True).exists()


def unsubscribe_all_emails(member) -> list[str]:
    """Turn off every subscribed address of ``member``; return the ids this call changed.

    Sends the unsubscribe confirmation when at least one address changed.
    """
    changed_ids, changed_at = _set_subscribe(member, ContactEmail.objects.filter(subscribe=True), subscribe=False)
    if changed_ids:
        send_subscription_confirmation(
            member=member,
            action="unsubscribe",
            email_ids=changed_ids,
            changed_at=changed_at,
        )
    return changed_ids


def resubscribe_emails(member, email_ids) -> list[str]:
    """Turn ``email_ids`` of ``member`` back on (``None``: the primary address); return the ids changed.

    Ids that no longer belong to the member are ignored. Sends the resubscribe confirmation when at least one
    address changed.
    """
    if email_ids is None:
        targets = ContactEmail.objects.filter(email_type="primary")
    else:
        targets = ContactEmail.objects.filter(pk__in=email_ids)
    changed_ids, changed_at = _set_subscribe(member, targets.filter(subscribe=False), subscribe=True)
    if changed_ids:
        send_subscription_confirmation(
            member=member,
            action="resubscribe",
            email_ids=changed_ids,
            changed_at=changed_at,
        )
    return changed_ids


def _set_subscribe(member, candidates, *, subscribe: bool):
    """Flip the member's ``candidates`` rows to ``subscribe`` under lock; return ``(changed ids, change time)``."""
    changed_at = timezone.now()
    with transaction.atomic():
        if Member.objects.select_for_update().filter(pk=member.pk).first() is None:
            return [], changed_at
        ids = list(candidates.select_for_update().filter(member=member).values_list("pk", flat=True))
        if ids:
            ContactEmail.objects.filter(pk__in=ids).update(subscribe=subscribe, updated_at=changed_at)
            # A bulk UPDATE sends no ``post_save``: schedule the member sheet sync that signal would have.
            schedule_member_sync_on_change(sender=ContactEmail)
    # Strings, not UUIDs: the ids go into signed (JSON) tokens and JSON job payloads.
    return [str(pk) for pk in ids], changed_at
