import re

from django.db import transaction

from apps.event.models import EventRegistration

from ....models import ContactPhone
from ....models.contact.phone_regions import PHONE_REGION_CHOICES
from ....services.contacts.contact_phones import (
    infer_region_from_e164,
    national_to_e164,
    normalize_to_national,
)


def compute_phone_changes():
    region_dict = dict(PHONE_REGION_CHOICES)
    phone_changes = []
    seen_normalized: dict[str, dict] = {}

    for contact_phone in ContactPhone.objects.select_related("member").order_by("created_at"):
        phone_changes.append(_build_phone_change(contact_phone, region_dict, seen_normalized))

    return phone_changes, _build_registration_phone_changes()


def apply_phone_changes(phone_changes, registration_changes) -> tuple[int, int, int]:
    updated_phones = 0
    deleted_duplicates = 0
    updated_registrations = 0

    with transaction.atomic():
        # Delete the duplicates FIRST. ContactPhone.phone_number is globally unique, and the changes
        # are ordered by created_at, so updating the older row to its normalized value while a newer
        # row still holds that exact value raised IntegrityError — the blanket except in
        # ContactPhoneAdmin._normalize_apply_view then swallowed it and the whole run rolled back, so
        # the tool could never fix anything.
        for change in phone_changes:
            if change["is_duplicate"]:
                ContactPhone.objects.filter(pk=change["pk"]).delete()
                deleted_duplicates += 1

        for change in phone_changes:
            if change["is_duplicate"]:
                continue
            if change["changed"]:
                ContactPhone.objects.filter(pk=change["pk"]).update(
                    phone_number=change["new_number"],
                    region=change["new_region"],
                )
                updated_phones += 1

        for change in registration_changes:
            EventRegistration.objects.filter(pk=change["pk"]).update(
                attendee_phone=change["new_phone"],
            )
            updated_registrations += 1

    return updated_phones, deleted_duplicates, updated_registrations


def build_normalization_message(updated_phones, deleted_duplicates, updated_regs):
    parts = []
    if updated_phones:
        parts.append(f"{updated_phones} phone(s) normalized")
    if deleted_duplicates:
        parts.append(f"{deleted_duplicates} duplicate(s) removed")
    if updated_regs:
        parts.append(f"{updated_regs} event registration phone(s) cleaned")
    if not parts:
        parts.append("No changes needed")
    return ". ".join(parts) + "."


def _build_phone_change(contact_phone, region_dict, seen_normalized):
    new_region = infer_region_from_e164(contact_phone.phone_number, contact_phone.region)
    new_number = normalize_to_national(contact_phone.phone_number, new_region)
    dedup_key = f"{new_region}:{new_number}"
    duplicate_of = seen_normalized.get(dedup_key)
    if duplicate_of is None:
        seen_normalized[dedup_key] = {
            "pk": str(contact_phone.pk),
            "member": str(contact_phone.member) if contact_phone.member else "-",
        }

    return {
        "pk": str(contact_phone.pk),
        "member": str(contact_phone.member) if contact_phone.member else "-",
        "old_number": contact_phone.phone_number,
        "new_number": new_number,
        "old_region": contact_phone.region,
        "old_region_display": region_dict.get(contact_phone.region, contact_phone.region),
        "new_region": new_region,
        "new_region_display": region_dict.get(new_region, new_region),
        "number_changed": new_number != contact_phone.phone_number,
        "region_changed": new_region != contact_phone.region,
        "is_duplicate": duplicate_of is not None,
        "duplicate_of": duplicate_of,
        "changed": (new_number != contact_phone.phone_number or new_region != contact_phone.region),
    }


def _build_registration_phone_changes():
    changes = []
    for registration in EventRegistration.objects.exclude(attendee_phone="").only(
        "pk",
        "attendee_phone",
        "attendee_first_name",
        "attendee_last_name",
        "ticket_code",
    ):
        digits = re.sub(r"\D", "", registration.attendee_phone.strip())
        if not digits:
            continue
        # Prefixing a bare "+" turned a national number into a *foreign* E.164 number: an
        # admin-entered "2095551234" became "+2095551234", which E164_RE accepts and the SMS sender
        # then dials as +20 (Egypt). Resolve the region first, exactly like the ContactPhone path.
        region = infer_region_from_e164(registration.attendee_phone)
        national = normalize_to_national(registration.attendee_phone, region)
        if not national:
            continue
        new_phone = national_to_e164(national, region)
        if new_phone == registration.attendee_phone:
            continue
        changes.append(
            {
                "pk": str(registration.pk),
                "ticket_code": registration.ticket_code,
                "attendee": _attendee_name(registration),
                "old_phone": registration.attendee_phone,
                "new_phone": new_phone,
            }
        )
    return changes


def _attendee_name(registration):
    return f"{registration.attendee_first_name} {registration.attendee_last_name}".strip() or "-"
