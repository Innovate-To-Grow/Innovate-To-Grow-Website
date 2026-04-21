"""
Sync event registration data back to the member's Django account.

Updates: first_name, last_name, and creates ContactPhone if phone was collected.
"""

import logging

from django.db import IntegrityError

from authn.models import ContactPhone
from authn.services.contacts.contact_phones import infer_region_from_e164, normalize_to_national

logger = logging.getLogger(__name__)


def sync_name_to_account(member, first_name: str, last_name: str) -> None:
    """Update the member's first_name and last_name from the registration form.

    Only non-empty incoming values overwrite existing values — never clear a
    previously-set name by passing in a blank string.
    """
    changed = False
    if first_name and first_name != member.first_name:
        member.first_name = first_name
        changed = True
    if last_name and last_name != member.last_name:
        member.last_name = last_name
        changed = True
    if changed:
        member.save(update_fields=["first_name", "last_name", "updated_at"])
        logger.info("Synced name to member %s: %s %s", member.pk, first_name, last_name)

        try:
            from authn.services.member_sheet_sync import schedule_member_sync

            schedule_member_sync()
        except Exception:
            # Best-effort: the member name was already persisted above; a
            # sheet-sync failure must not break the registration flow.
            logger.debug("schedule_member_sync failed after name sync", exc_info=True)


def sync_phone_to_account(member, phone_number: str, *, region: str = "1-US", verified: bool = False) -> None:
    """Sync event registration phone to the member's ContactPhone.

    Conflict rules (same pattern as sync_secondary_email_to_account):
    - Already on this member → update verified status if needed.
    - Owned by a different member → skip (don't steal).
    - Brand new → create.
    - Race condition → swallow IntegrityError.
    """
    if not phone_number or not phone_number.strip():
        return

    region = infer_region_from_e164(phone_number.strip(), region)
    national = normalize_to_national(phone_number.strip(), region)

    existing = ContactPhone.objects.filter(phone_number=national).first()
    if existing:
        if existing.member_id == member.pk:
            if verified and not existing.verified:
                existing.verified = True
                existing.save(update_fields=["verified", "updated_at"])
                logger.info("Marked phone %s as verified for member %s.", national, member.pk)
        else:
            logger.info("Phone %s belongs to another member, not syncing to member %s.", national, member.pk)
        return

    try:
        ContactPhone.objects.create(
            member=member,
            phone_number=national,
            region=region,
            verified=verified,
        )
        logger.info("Synced phone %s to member %s account.", national, member.pk)
    except IntegrityError:
        logger.warning("Phone %s was claimed concurrently, skipping sync for member %s.", national, member.pk)
