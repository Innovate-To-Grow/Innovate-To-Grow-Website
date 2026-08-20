"""Update helpers for member imports."""

from __future__ import annotations

from collections.abc import Callable

from django.db import transaction
from django.db.models.functions import Lower

from apps.authn.models import ContactEmail, ContactPhone
from apps.authn.services.contacts.contact_phones import infer_region_from_e164, normalize_to_national

from .types import ImportResult

# Model defaults, used when a brand-new contact row is created and the sheet supplies no flag.
_EMAIL_DEFAULTS = {"verified": False, "subscribe": True}
_PHONE_DEFAULTS = {"verified": False, "subscribe": False}

STAFF_COLUMN_IGNORED = "Staff column ignored (only an I2G Master may change staff status)"


def _flag(parsed_value, current, default):
    """Apply the sheet's flag, or keep what is stored when the sheet does not supply one."""
    if parsed_value is not None:
        return parsed_value
    return default if current is None else current


def bulk_update_members(
    rows: list[dict],
    result: ImportResult,
    claimed_contact_emails: set[str],
    claimed_phones: set[str],
    update_member_allowed: Callable[[object], bool] | None = None,
    allow_privilege_fields: bool = False,
):
    emails = [row["primary_email"] for row in rows]
    contacts = (
        ContactEmail.objects.annotate(email_lower=Lower("email_address"))
        .filter(email_lower__in=[e.lower() for e in emails], email_type="primary")
        .select_related("member")
    )
    member_map = {contact.email_address.lower(): contact.member for contact in contacts if contact.member}

    for parsed in rows:
        member = member_map.get(parsed["primary_email"].lower())
        if not member:
            result.skipped_count += 1
            # Say why: the address may exist only as a secondary or unowned ContactEmail, which is
            # indistinguishable from a typo without a message.
            result.errors.append(f"Row {parsed['row']}: no member has {parsed['primary_email']} as their primary email")
            continue
        if update_member_allowed is not None and not update_member_allowed(member):
            result.skipped_count += 1
            result.errors.append(f"Row {parsed['row']}: You do not have permission to update this member")
            continue
        try:
            with transaction.atomic():
                update_single_member(
                    member,
                    parsed,
                    claimed_contact_emails,
                    claimed_phones,
                    allow_privilege_fields=allow_privilege_fields,
                )
            result.updated_count += 1
            if parsed["is_staff"] is not None and not allow_privilege_fields:
                result.errors.append(f"Row {parsed['row']}: {STAFF_COLUMN_IGNORED}")
        except Exception as exc:  # noqa: BLE001
            result.skipped_count += 1
            result.errors.append(f"Row {parsed['row']}: {exc}")


def update_single_member(
    member,
    parsed,
    claimed_contact_emails,
    claimed_phones,
    allow_privilege_fields: bool = False,
):
    if parsed["first_name"]:
        member.first_name = parsed["first_name"]
    if parsed["last_name"]:
        member.last_name = parsed["last_name"]
    if parsed["middle_name"]:
        member.middle_name = parsed["middle_name"]
    if parsed["title"]:
        member.title = parsed["title"]
    if parsed["organization"]:
        member.organization = parsed["organization"]
    if parsed["is_active"] is not None:
        member.is_active = parsed["is_active"]
    # ``is_staff`` is an I2G Master responsibility (see MemberAdmin.superuser_only_fields). The
    # export writes a Staff column, so without this gate the export -> edit -> re-import round trip
    # was a way for any authn-app admin to mint staff accounts or lock the superuser out.
    if parsed["is_staff"] is not None and allow_privilege_fields:
        member.is_staff = parsed["is_staff"]
    member.save()

    primary_contact = member.contact_emails.filter(email_type="primary").first()
    primary_email = primary_contact.email_address if primary_contact else parsed["primary_email"]
    email_key = primary_email.lower()
    if email_key not in claimed_contact_emails:
        existing = ContactEmail.objects.filter(member=member, email_address__iexact=primary_email).first()
        if existing:
            existing.verified = _flag(parsed["primary_verified"], existing.verified, _EMAIL_DEFAULTS["verified"])
            existing.subscribe = _flag(parsed["primary_subscribed"], existing.subscribe, _EMAIL_DEFAULTS["subscribe"])
            existing.email_type = "primary"
            existing.save(update_fields=["verified", "subscribe", "email_type", "updated_at"])
        else:
            ContactEmail.objects.create(
                member=member,
                email_address=primary_email,
                email_type="primary",
                verified=_flag(parsed["primary_verified"], None, _EMAIL_DEFAULTS["verified"]),
                subscribe=_flag(parsed["primary_subscribed"], None, _EMAIL_DEFAULTS["subscribe"]),
            )
        claimed_contact_emails.add(email_key)
    else:
        current = ContactEmail.objects.filter(member=member, email_address__iexact=primary_email).first()
        if current is not None:
            current.email_type = "primary"
            current.verified = _flag(parsed["primary_verified"], current.verified, _EMAIL_DEFAULTS["verified"])
            current.subscribe = _flag(parsed["primary_subscribed"], current.subscribe, _EMAIL_DEFAULTS["subscribe"])
            current.save(update_fields=["email_type", "verified", "subscribe", "updated_at"])

    if parsed["secondary_email"]:
        secondary_key = parsed["secondary_email"].lower()
        member.contact_emails.filter(email_type="secondary").exclude(
            email_address__iexact=parsed["secondary_email"]
        ).delete()
        if secondary_key not in claimed_contact_emails:
            existing_sec = ContactEmail.objects.filter(
                member=member, email_address__iexact=parsed["secondary_email"]
            ).first()
            if existing_sec:
                existing_sec.email_type = "secondary"
                existing_sec.verified = _flag(
                    parsed["secondary_verified"], existing_sec.verified, _EMAIL_DEFAULTS["verified"]
                )
                existing_sec.subscribe = _flag(
                    parsed["secondary_subscribed"], existing_sec.subscribe, _EMAIL_DEFAULTS["subscribe"]
                )
                existing_sec.save(update_fields=["email_type", "verified", "subscribe", "updated_at"])
            else:
                ContactEmail.objects.create(
                    member=member,
                    email_address=parsed["secondary_email"],
                    email_type="secondary",
                    verified=_flag(parsed["secondary_verified"], None, _EMAIL_DEFAULTS["verified"]),
                    subscribe=_flag(parsed["secondary_subscribed"], None, _EMAIL_DEFAULTS["subscribe"]),
                )
            claimed_contact_emails.add(secondary_key)
    elif parsed.get("has_secondary_email_column"):
        # Blank cell in a column the sheet does have = "remove it". A sheet without the column at all
        # must not delete anything; deletes here are hard and unrecoverable.
        member.contact_emails.filter(email_type="secondary").delete()

    if parsed["phone_number"]:
        region = infer_region_from_e164(parsed["phone_number"])
        national = normalize_to_national(parsed["phone_number"], region)
        if national not in claimed_phones:
            existing_phone = member.contact_phones.first()
            if existing_phone:
                existing_phone.phone_number = national
                existing_phone.region = region
                existing_phone.subscribe = _flag(
                    parsed["phone_subscribed"], existing_phone.subscribe, _PHONE_DEFAULTS["subscribe"]
                )
                existing_phone.verified = _flag(
                    parsed["phone_verified"], existing_phone.verified, _PHONE_DEFAULTS["verified"]
                )
                existing_phone.save()
            else:
                ContactPhone.objects.create(
                    member=member,
                    phone_number=national,
                    region=region,
                    subscribe=_flag(parsed["phone_subscribed"], None, _PHONE_DEFAULTS["subscribe"]),
                    verified=_flag(parsed["phone_verified"], None, _PHONE_DEFAULTS["verified"]),
                )
            claimed_phones.add(national)
    elif parsed.get("has_phone_column"):
        member.contact_phones.all().delete()
