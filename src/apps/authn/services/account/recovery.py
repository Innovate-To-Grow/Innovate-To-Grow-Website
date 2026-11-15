"""Recovery-contact helpers shared by the password and email-deletion flows."""

from __future__ import annotations

from apps.authn.models import ContactEmail, ContactPhone
from apps.authn.services.email.challenges import AuthChallengeError


class LastRecoveryContactError(AuthChallengeError):
    """Raised when deleting an email would remove the member's last verified recovery contact."""


class NoRecoveryChannelError(AuthChallengeError):
    """Raised when a member has no verified email or phone to verify a password create/change."""


def count_verified_recovery_contacts(member, *, exclude_email_pk=None, exclude_phone_pk=None) -> int:
    """Count the member's verified recovery contacts: verified emails + verified phones.

    A verified phone is a first-class recovery contact, so a phone-only account
    with a verified phone and no emails still has a non-zero count. ``exclude_email_pk``
    / ``exclude_phone_pk`` let callers ask "what would remain after deleting this contact?".
    """
    emails = ContactEmail.objects.filter(member=member, verified=True)
    if exclude_email_pk is not None:
        emails = emails.exclude(pk=exclude_email_pk)
    phones = ContactPhone.objects.filter(member=member, verified=True)
    if exclude_phone_pk is not None:
        phones = phones.exclude(pk=exclude_phone_pk)
    return emails.count() + phones.count()


def members_with_sign_in_contact(member_ids) -> set:
    """Of ``member_ids``, the members who have at least one verified email or phone (a way to sign in).

    The admin compares this before and after a change to warn when a member is left with none (see
    ``apps.authn.admin.members.sign_in_warning``).
    """
    ids = {pk for pk in member_ids if pk is not None}
    if not ids:
        return set()
    emails = ContactEmail.objects.filter(member_id__in=ids, verified=True).values_list("member_id", flat=True)
    phones = ContactPhone.objects.filter(member_id__in=ids, verified=True).values_list("member_id", flat=True)
    return set(emails) | set(phones)
