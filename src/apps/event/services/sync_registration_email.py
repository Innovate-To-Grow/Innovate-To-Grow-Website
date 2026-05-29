import logging

from django.db import IntegrityError

from authn.models import ContactEmail

logger = logging.getLogger(__name__)


def sync_secondary_email_to_account(member, email_address: str) -> None:
    """Sync event registration secondary email to the member's account.

    Conflict rules:
    - Already on this member → skip.
    - Owned by a different member → skip (don't steal).
    - Brand new → create as unverified secondary.
    - Race condition (concurrent create) → swallow IntegrityError.
    """
    if not email_address or not email_address.strip():
        return

    normalized = email_address.strip().lower()

    existing = ContactEmail.objects.filter(email_address__iexact=normalized).first()
    if existing:
        if existing.member_id == member.pk:
            logger.debug("Secondary email %s already belongs to member %s, skipping.", normalized, member.pk)
        else:
            logger.info(
                "Secondary email %s belongs to another member, not syncing to member %s.",
                normalized,
                member.pk,
            )
        return

    try:
        ContactEmail.objects.create(
            member=member,
            email_address=normalized,
            email_type="secondary",
            verified=False,
        )
        logger.info("Synced secondary email %s to member %s account.", normalized, member.pk)
    except IntegrityError:
        logger.warning(
            "Secondary email %s was claimed concurrently, skipping sync for member %s.", normalized, member.pk
        )
