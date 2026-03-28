"""Update helpers for member imports."""

from __future__ import annotations

from django.db import transaction

from authn.models import ContactEmail, ContactPhone

from .types import ImportResult


def bulk_update_members(
    rows: list[dict],
    result: ImportResult,
    claimed_contact_emails: set[str],
    claimed_phones: set[str],
):
    emails = [row["primary_email"] for row in rows]
    contacts = ContactEmail.objects.filter(email_address__in=emails, email_type="primary").select_related("member")
    member_map = {contact.email_address.lower(): contact.member for contact in contacts if contact.member}

    for parsed in rows:
        member = member_map.get(parsed["primary_email"].lower())
        if not member:
            result.skipped_count += 1
            continue
        try:
            with transaction.atomic():
                update_single_member(member, parsed, claimed_contact_emails, claimed_phones)
            result.updated_count += 1
        except Exception as exc:  # noqa: BLE001
            result.skipped_count += 1
            result.errors.append(f"Row {parsed['row']}: {exc}")


def update_single_member(member, parsed, claimed_contact_emails, claimed_phones):
    if parsed["first_name"]:
        member.first_name = parsed["first_name"]
    if parsed["last_name"]:
        member.last_name = parsed["last_name"]
    if parsed["organization"]:
        member.organization = parsed["organization"]
    member.email_subscribe = parsed["primary_subscribed"]
    member.save()

    primary_contact = member.contact_emails.filter(email_type="primary").first()
    primary_email = primary_contact.email_address if primary_contact else parsed["primary_email"]
    email_key = primary_email.lower()
    if email_key not in claimed_contact_emails:
        ContactEmail.objects.update_or_create(
            member=member,
            email_address=primary_email,
            defaults={
                "email_type": "primary",
                "verified": parsed["primary_verified"],
                "subscribe": parsed["primary_subscribed"],
            },
        )
        claimed_contact_emails.add(email_key)
    else:
        ContactEmail.objects.filter(member=member, email_address=primary_email).update(
            verified=parsed["primary_verified"],
            subscribe=parsed["primary_subscribed"],
        )

    if parsed["secondary_email"]:
        secondary_key = parsed["secondary_email"].lower()
        member.contact_emails.filter(email_type="secondary").exclude(email_address=parsed["secondary_email"]).delete()
        if secondary_key not in claimed_contact_emails:
            ContactEmail.objects.update_or_create(
                member=member,
                email_address=parsed["secondary_email"],
                defaults={
                    "email_type": "secondary",
                    "verified": parsed["secondary_verified"],
                    "subscribe": parsed["secondary_subscribed"],
                },
            )
            claimed_contact_emails.add(secondary_key)
    else:
        member.contact_emails.filter(email_type="secondary").delete()

    if parsed["phone_number"]:
        if parsed["phone_number"] not in claimed_phones:
            existing_phone = member.contact_phones.first()
            if existing_phone:
                existing_phone.phone_number = parsed["phone_number"]
                existing_phone.subscribe = parsed["phone_subscribed"]
                existing_phone.verified = parsed["phone_verified"]
                existing_phone.save()
            else:
                ContactPhone.objects.create(
                    member=member,
                    phone_number=parsed["phone_number"],
                    region="US",
                    subscribe=parsed["phone_subscribed"],
                    verified=parsed["phone_verified"],
                )
            claimed_phones.add(parsed["phone_number"])
    else:
        member.contact_phones.all().delete()
