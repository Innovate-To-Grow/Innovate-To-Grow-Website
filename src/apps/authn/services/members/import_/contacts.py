"""The contact changes an import may make to an existing member.

An import adds contacts. It never deletes one, overwrites one in place, moves one between members, re-subscribes
one, or un-verifies one. A blank cell and a missing column both leave the stored records alone. Everything a row
asked for but did not get is returned as a note for the import report.

Nothing here sends mail or SMS: contacts are written directly, never through ``create_contact_email``, which emails
a verification code.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from apps.authn.models import ContactEmail, ContactPhone
from apps.authn.services.contacts.contact_phones import infer_region_from_e164, normalize_to_national

from .matching import UNLINKED_EMAIL, UNLINKED_PHONE, member_label

NEVER_DELETES = "an import never deletes a contact"
NEVER_MOVES = "an import never moves a contact from one member to another"
NEVER_RESUBSCRIBES = "an import never re-subscribes"
NEVER_UNVERIFIES = "an import never un-verifies a contact"
STARTS_UNVERIFIED = "contacts added to an existing member start unverified; the member verifies them on /account"
_EMAIL_MAX_LENGTH = ContactEmail._meta.get_field("email_address").max_length


def valid_new_address(address: str) -> bool:
    """Whether ``address`` may be stored as a new contact email (the bulk paths skip model validation)."""
    if len(address) > _EMAIL_MAX_LENGTH:
        return False
    try:
        validate_email(address)
    except ValidationError:
        return False
    return True


def phone_parts(raw: str | None) -> tuple[str, str]:
    """``(national digits, region)`` for a cleaned Phone Number cell; ``("", "")`` when there is none."""
    if not raw:
        return "", ""
    region = infer_region_from_e164(raw)
    return normalize_to_national(raw, region), region


def apply_primary_flags(contact: ContactEmail, parsed: dict, notes: list[str]) -> None:
    """Apply the Primary Verified/Subscribed cells to the address the Primary Email cell names, safe direction only.

    TRUE marks the address verified, as the Contact Emails "Mark verified" action can, and FALSE unsubscribes it,
    which honours an opt-out. Un-verifying could lock the member out of sign-in and re-subscribing would override an
    opt-out, so those two are reported instead.
    """
    changed = []
    verified, subscribe = parsed["primary_verified"], parsed["primary_subscribed"]
    if verified is True and not contact.verified:
        contact.verified = True
        changed.append("verified")
    elif verified is False and contact.verified:
        notes.append(
            f"Primary Verified is FALSE, but {contact.email_address} is verified; left verified ({NEVER_UNVERIFIES})"
        )
    if subscribe is False and contact.subscribe:
        contact.subscribe = False
        changed.append("subscribe")
    elif subscribe is True and not contact.subscribe:
        notes.append(
            f"Primary Subscribed is TRUE, but {contact.email_address} is unsubscribed; left unsubscribed "
            f"({NEVER_RESUBSCRIBES})"
        )
    if changed:
        contact.save(update_fields=[*changed, "updated_at"])


def sync_secondary_email(member, parsed: dict, notes: list[str]) -> None:
    """Add the Secondary Email cell's address to ``member``; keep every address the member already has."""
    address = parsed["secondary_email"]
    if not address:
        # A blank cell used to delete every secondary. Say what was kept, so nobody relies on that any more.
        if parsed.get("has_secondary_email_column"):
            secondaries = member.contact_emails.filter(email_type="secondary").values_list("email_address", flat=True)
            _report_kept("Secondary Email", list(secondaries), notes)
        return
    if address.lower() == parsed["primary_email"].lower():
        notes.append("Secondary Email is the same as the Primary Email; ignored")
        return
    holders = list(ContactEmail.objects.filter(email_address__iexact=address).select_related("member"))
    if holders:
        _report_existing_secondary(member, parsed, holders, notes)
    elif not valid_new_address(address):
        notes.append(f"Secondary Email {address!r} is not a valid email address; ignored")
    else:
        _add_secondary(member, parsed, address, notes)


def sync_phone(member, parsed: dict, notes: list[str]) -> None:
    """Add the Phone Number cell's number to ``member``; keep every number the member already has."""
    if not parsed["phone_number"]:
        if parsed.get("has_phone_column"):
            _report_kept("Phone Number", [phone.to_e164() for phone in member.contact_phones.all()], notes)
        return
    national, region = phone_parts(parsed["phone_number"])
    if not national:
        notes.append(f"Phone Number {parsed['phone_number']} has no digits after the country code; ignored")
        return
    holder = ContactPhone.objects.filter(phone_number=national).select_related("member").first()
    if holder is None:
        _add_phone(member, parsed, ContactPhone(member=member, phone_number=national, region=region), notes)
    elif holder.member_id is None:
        notes.append(f"Phone Number {holder.to_e164()} is {UNLINKED_PHONE}; not added")
    elif holder.member_id != member.pk:
        notes.append(
            f"Phone Number {holder.to_e164()} belongs to {member_label(holder.member)}; not added ({NEVER_MOVES})"
        )
    else:
        _report_unapplied_flags(
            holder, holder.to_e164(), "Phone", parsed["phone_verified"], parsed["phone_subscribed"], notes
        )


def _report_kept(column: str, kept: list[str], notes: list[str]) -> None:
    if kept:
        notes.append(f"{column} is blank; kept {', '.join(kept)} ({NEVER_DELETES})")


def _report_existing_secondary(member, parsed: dict, holders: list[ContactEmail], notes: list[str]) -> None:
    address = parsed["secondary_email"]
    holder = holders[0]
    if len(holders) > 1:
        notes.append(
            f"Secondary Email {address} matches {len(holders)} contact emails that differ only in letter case; "
            "not added (merge them under Contact Emails)"
        )
    elif holder.member_id is None:
        notes.append(f"Secondary Email {address} is {UNLINKED_EMAIL}; not added (link it under Contact Emails)")
    elif holder.member_id != member.pk:
        notes.append(f"Secondary Email {address} belongs to {member_label(holder.member)}; not added ({NEVER_MOVES})")
    elif holder.email_type != "secondary":
        notes.append(f'Secondary Email {address} is already this member\'s "{holder.email_type}" email; left as it is')
    else:
        verified, subscribe = parsed["secondary_verified"], parsed["secondary_subscribed"]
        _report_unapplied_flags(holder, holder.email_address, "Secondary", verified, subscribe, notes)


def _report_unapplied_flags(contact, label: str, column: str, verified, subscribe, notes: list[str]) -> None:
    """Flag cells are not applied to a secondary email or phone the member already has (as before); say so."""
    cells = [
        f"{column} {name}"
        for name, sheet, stored in (
            ("Verified", verified, contact.verified),
            ("Subscribed", subscribe, contact.subscribe),
        )
        if sheet is not None and sheet != stored
    ]
    if cells:
        notes.append(f"{' and '.join(cells)} not applied to the existing {label}; change it on the member page")


def _add_secondary(member, parsed: dict, address: str, notes: list[str]) -> None:
    """Make ``address`` the member's secondary email. A previous secondary becomes "other"; nothing is deleted."""
    previous = list(member.contact_emails.filter(email_type="secondary"))
    subscribe = _new_contact_subscribe(
        parsed["secondary_subscribed"],
        default=True,
        allowed=member.contact_emails.filter(subscribe=True).exists(),
        refusal=f"{address} was added unsubscribed: the member is unsubscribed at every other address",
        notes=notes,
    )
    for contact in previous:
        contact.email_type = "other"
        contact.save(update_fields=["email_type", "updated_at"])
    ContactEmail.objects.create(
        member=member, email_address=address, email_type="secondary", verified=False, subscribe=subscribe
    )
    if previous:
        kept = ", ".join(contact.email_address for contact in previous)
        notes.append(f'Added {address} as the secondary email; kept the previous secondary {kept} as "other"')
    if parsed["secondary_verified"]:
        notes.append(f"{address} was added unverified ({STARTS_UNVERIFIED})")


def _add_phone(member, parsed: dict, phone: ContactPhone, notes: list[str]) -> None:
    """Add ``phone`` next to the member's numbers. It never replaces one, so it never inherits "verified"."""
    existing = list(member.contact_phones.all())
    label = phone.to_e164()
    phone.verified = False
    phone.subscribe = _new_contact_subscribe(
        parsed["phone_subscribed"],
        default=False,
        allowed=not existing or any(other.subscribe for other in existing),
        refusal=f"{label} was added unsubscribed: the member's other phone numbers are unsubscribed",
        notes=notes,
    )
    phone.save()
    if existing:
        kept = ", ".join(other.to_e164() for other in existing)
        notes.append(f"Added {label} as an additional phone number; kept {kept} (an import never replaces a number)")
    if parsed["phone_verified"]:
        notes.append(f"{label} was added unverified ({STARTS_UNVERIFIED})")


def _new_contact_subscribe(sheet_value, *, default: bool, allowed: bool, refusal: str, notes: list[str]) -> bool:
    """Subscribed flag for a contact added to an existing member.

    The sheet's value, else the model default; but never on when the member has opted out on that channel (no
    subscribed address, or only unsubscribed phone numbers), as the event-registration email sync also decides.
    """
    wanted = default if sheet_value is None else sheet_value
    if wanted and not allowed:
        if sheet_value:
            notes.append(f"{refusal} ({NEVER_RESUBSCRIBES})")
        return False
    return wanted
