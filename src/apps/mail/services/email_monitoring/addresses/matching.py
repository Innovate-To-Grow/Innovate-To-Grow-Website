"""Which contact emails and members an address belongs to, read live (the cached links on ``BouncedAddress`` are only
for filtering).

``ContactEmail.email_address`` is unique as written, so legacy rows can hold one address in two letter cases, even on
two members. Such an address is **ambiguous**: no action that changes a contact or a member applies to it until the
duplicates are resolved in Contact Emails.
"""

from dataclasses import dataclass, field

from django.db.models.functions import Lower

from apps.authn.models import ContactEmail
from apps.mail.models import BouncedAddress

Role = BouncedAddress.Role
MEMBER_ROLES = frozenset({Role.PRIMARY, Role.SECONDARY, Role.OTHER})
_EMAIL_TYPES = {"primary": Role.PRIMARY, "secondary": Role.SECONDARY, "other": Role.OTHER}


@dataclass
class AddressMatch:
    address: str
    contacts: list = field(default_factory=list)

    @property
    def role(self) -> str:
        if not self.contacts:
            return Role.NONE
        if len(self.contacts) > 1:
            return Role.AMBIGUOUS
        contact = self.contacts[0]
        if contact.member_id is None:
            return Role.UNLINKED
        return _EMAIL_TYPES.get(contact.email_type, Role.OTHER)

    @property
    def contact(self):
        """The one contact email, when there is exactly one."""
        return self.contacts[0] if len(self.contacts) == 1 else None

    @property
    def member(self):
        """The one member, when the address is exactly one member's contact email."""
        contact = self.contact
        return contact.member if contact is not None else None

    @property
    def owners(self) -> list:
        """Every member holding the address (several only when it is ambiguous), in a stable order."""
        found = {contact.member_id: contact.member for contact in self.contacts if contact.member_id is not None}
        return [found[key] for key in sorted(found, key=str)]


def match_addresses(addresses) -> dict[str, AddressMatch]:
    """``{address: AddressMatch}`` for the given lower-case addresses, in one query."""
    wanted = {address for address in addresses if address}
    matches = {address: AddressMatch(address) for address in wanted}
    if not wanted:
        return matches
    contacts = (
        ContactEmail.objects.annotate(normalized=Lower("email_address"))
        .filter(normalized__in=wanted)
        .select_related("member")
        .order_by("created_at", "pk")
    )
    for contact in contacts:
        matches[contact.normalized].contacts.append(contact)
    return matches


def match_address(address: str) -> AddressMatch:
    return match_addresses([address])[address] if address else AddressMatch(address)


def cached_links(match: AddressMatch) -> dict:
    """The cached values ``BouncedAddress`` keeps for filtering."""
    contact = match.contact
    return {
        "role": match.role,
        "contact_email_id": contact.pk if contact is not None else None,
        "member_id": contact.member_id if contact is not None else None,
    }


def refresh_cached_links(rows, matches: dict[str, AddressMatch] | None = None) -> int:
    """Write the live links of ``rows`` where the cache differs; return how many rows changed."""
    rows = list(rows)
    matches = matches if matches is not None else match_addresses(row.address for row in rows)
    changed = 0
    for row in rows:
        values = cached_links(matches.get(row.address) or AddressMatch(row.address))
        if any(getattr(row, name) != value for name, value in values.items()):
            BouncedAddress.objects.filter(pk=row.pk).update(**values)
            for name, value in values.items():
                setattr(row, name, value)
            changed += 1
    return changed
