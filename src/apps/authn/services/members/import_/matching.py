"""Who already holds an address the sheet names, said in words an admin can act on.

A row reaches an existing member only through that member's *primary* email. When the Primary Email cell names an
address that exists in any other way, the row is skipped, and these helpers say why: the address is another
member's secondary or "other" email (the "Row 5" case), a contact email linked to no member, or a legacy duplicate
that differs only in letter case.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from apps.authn.models import ContactEmail, ContactPhone

UNLINKED_EMAIL = "a contact email that is not linked to any member"
UNLINKED_PHONE = "a contact phone that is not linked to any member"


def lookup_contact_emails(addresses: Iterable[str | None]) -> dict[str, list[ContactEmail]]:
    """Every ContactEmail whose address equals one of ``addresses`` ignoring case, keyed by the lower-cased address.

    Both sides are folded with Python's ``str.lower``, the comparison the import has always used to route rows, so
    the routing and the matching can't disagree. The unique constraint on ``email_address`` is case-sensitive, so a
    key may hold several records: legacy duplicates that differ only in letter case.
    """
    wanted = {address.lower() for address in addresses if address}
    if not wanted:
        return {}
    pks = [pk for pk, address in ContactEmail.objects.values_list("pk", "email_address") if address.lower() in wanted]
    found: dict[str, list[ContactEmail]] = defaultdict(list)
    for contact in ContactEmail.objects.filter(pk__in=pks).select_related("member").order_by("created_at"):
        found[contact.email_address.lower()].append(contact)
    return dict(found)


def lookup_contact_phones(numbers: Iterable[str | None]) -> dict[str, ContactPhone]:
    """Every ContactPhone whose national digits are one of ``numbers``, keyed by those digits."""
    wanted = {number for number in numbers if number}
    if not wanted:
        return {}
    return {
        phone.phone_number: phone
        for phone in ContactPhone.objects.filter(phone_number__in=wanted).select_related("member")
    }


def member_label(member) -> str:
    """``Ada Lovelace (member <uuid>)``: a name to read and the UUID to search for under Members."""
    return f"{member.get_full_name() or 'Unnamed member'} (member {member.pk})"


def email_holder(contacts: list[ContactEmail]) -> str:
    """Who holds an address, for "already used by …": a member, nobody, or several case-only duplicates."""
    if len(contacts) > 1:
        return f"{len(contacts)} existing contact emails that differ only in letter case"
    contact = contacts[0]
    return member_label(contact.member) if contact.member_id else UNLINKED_EMAIL


def phone_holder(phone: ContactPhone) -> str:
    return member_label(phone.member) if phone.member_id else UNLINKED_PHONE


def update_skip_reason(address: str, matches: list[ContactEmail]):
    """Why "Update Existing Members" found no member for a Primary Email cell, what to do, and who it is about.

    The Row 5 message: ``no member has x as their primary email: it is the secondary email of Neil Parkhi
    (member …), whose primary email is y. Row not imported. …``.
    """
    if len(matches) > 1:
        return _duplicates_reason(address, matches), None
    member = matches[0].member if matches else None
    status = f"it is {_role(matches[0])}" if matches else "no contact email has this address any more"
    return f"no member has {address} as their primary email: {status}. Row not imported{_hint(matches)}", member


def create_only_skip_reason(address: str, matches: list[ContactEmail]):
    """Why a row whose Primary Email already exists was skipped while "Update Existing Members" is off."""
    if len(matches) > 1:
        return _duplicates_reason(address, matches), None
    contact = matches[0]
    if contact.member is not None and contact.email_type == "primary":
        return (
            f"Member with email {address} already exists: {member_label(contact.member)}. Skipped because "
            '"Update Existing Members" is off',
            contact.member,
        )
    return f"{address} already exists: it is {_role(contact)}. Row not imported{_hint(matches)}", contact.member


def _duplicates_reason(address: str, matches: list[ContactEmail]) -> str:
    holders = "; ".join(f"{contact.email_address} is {_role(contact)}" for contact in matches)
    return (
        f"{address} matches {len(matches)} contact emails that differ only in letter case ({holders}). Row not "
        "imported: merge the duplicates under Contact Emails first"
    )


def _role(contact: ContactEmail) -> str:
    if contact.member is None:
        return UNLINKED_EMAIL
    role = f"the {contact.email_type} email of {member_label(contact.member)}"
    if contact.email_type == "primary":
        return role
    return f"{role}, whose primary email is {contact.member.get_primary_email() or '(none)'}"


def _hint(matches: list[ContactEmail]) -> str:
    if not matches:
        return ""
    if matches[0].member is None:
        return ": link it to a member (or delete it) under Contact Emails first"
    return (
        ". Rows are matched to existing members by primary email only: put the member's primary email in the "
        "Primary Email cell, or make this address their primary email on the member page first"
    )
