"""Changes that take the member lock: deleting a contact email (never the last verified recovery contact) and making a
verified one the primary."""

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.authn.models import ContactEmail
from apps.authn.services.account.recovery import (
    LastRecoveryContactError,
    count_verified_recovery_contacts,
)
from apps.authn.services.email.challenges import (
    AuthChallengeInvalid,
)

Member = get_user_model()


@transaction.atomic
def delete_contact_email(*, member, contact_email_id):
    """Delete a contact email, enforcing the recovery-contact and primary invariants.

    Deletion is blocked when it would remove the member's last verified recovery
    contact (a verified phone or another verified email counts as a survivor). If
    the deleted email is the primary, another remaining email is promoted
    deterministically (prefer verified, else oldest); if no email remains, the
    account may legitimately have no primary (e.g. a phone-only account).
    """
    # The member row is the shared mutex for email and phone deletion. Locking
    # only the target contact cannot serialize cross-table "last recovery
    # method" checks.
    Member.objects.select_for_update().get(pk=member.pk)
    contact = ContactEmail.objects.select_for_update().filter(pk=contact_email_id, member=member).first()
    if contact is None:
        raise AuthChallengeInvalid("Contact email not found.")

    # Deleting an *unverified* email never reduces recovery capability, so only
    # guard verified emails. The guard checks what would remain *after* deletion.
    if contact.verified and count_verified_recovery_contacts(member, exclude_email_pk=contact.pk) == 0:
        raise LastRecoveryContactError(
            "You can't remove your only verified recovery method. Add and verify another email or phone first."
        )

    was_primary = contact.email_type == "primary"
    contact.delete()

    if was_primary:
        replacement = (
            ContactEmail.objects.select_for_update().filter(member=member).order_by("-verified", "created_at").first()
        )
        if replacement is not None:
            replacement.email_type = "primary"
            replacement.save(update_fields=["email_type", "updated_at"])


@transaction.atomic
def make_contact_email_primary(*, member, contact_email_id):
    """
    Set a verified non-primary contact email as primary.

    The previous primary becomes ``secondary`` (not deleted). Requires the target email to be verified.
    """
    Member.objects.select_for_update().get(pk=member.pk)
    contact = ContactEmail.objects.select_for_update().filter(pk=contact_email_id, member=member).first()
    if contact is None:
        raise AuthChallengeInvalid("Contact email not found.")

    if contact.email_type == "primary":
        return contact

    if not contact.verified:
        raise AuthChallengeInvalid("Verify this email before setting it as primary.")

    old_primary = (
        ContactEmail.objects.select_for_update()
        .filter(member=member, email_type="primary")
        .order_by("created_at")
        .first()
    )
    if old_primary:
        # Demote existing secondary to "other" before the old primary takes its slot
        # The newest secondary; ``pk`` breaks a tie on equal timestamps, so the choice is deterministic and the admin's
        # preview (``primary_switch.plan_primary_switch``) names the same row.
        existing_secondary = (
            ContactEmail.objects.select_for_update()
            .filter(member=member, email_type="secondary")
            .exclude(pk=contact.pk)
            .order_by("-created_at", "-pk")
            .first()
        )
        if existing_secondary:
            existing_secondary.email_type = "other"
            existing_secondary.save(update_fields=["email_type", "updated_at"])

        old_primary.email_type = "secondary"
        old_primary.save(update_fields=["email_type", "updated_at"])

    contact.email_type = "primary"
    contact.save(update_fields=["email_type", "updated_at"])

    return contact
