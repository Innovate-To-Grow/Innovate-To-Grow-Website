"""The records a review compares a sheet with: e-mails, phones and members as the database holds them."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from apps.authn.models import Member

from ...contacts import phone_parts

_DISPLAY_ONLY = ("created", "date_joined", "last_login")


def address_key(address: str | None) -> str:
    return (address or "").strip().upper().lower()


def us_phone(raw: str | None) -> tuple[str, str] | None:
    """``(national digits, region)`` for a 10-digit US number, else None (SMS is US-only)."""
    national, region = phone_parts(raw)
    if len(national) == 10 and national[0] in "23456789":
        return national, region
    return None


@dataclass(frozen=True)
class EmailRecord:
    id: str
    address: str
    type: str
    member: str | None
    verified: bool
    subscribe: bool
    created: str = ""


@dataclass(frozen=True)
class PhoneRecord:
    id: str
    number: str
    region: str
    member: str | None
    verified: bool
    subscribe: bool
    created: str = ""

    @property
    def e164(self) -> str:
        return f"+{self.region.split('-')[0]}{self.number}"


@dataclass
class MemberRecord:
    id: str
    first_name: str = ""
    middle_name: str = ""
    last_name: str = ""
    organization: str = ""
    title: str = ""
    is_active: bool = True
    is_staff: bool = False
    is_superuser: bool = False
    registration_pending: bool = False
    emails: list[EmailRecord] = field(default_factory=list)
    phones: list[PhoneRecord] = field(default_factory=list)
    date_joined: str = ""
    last_login: str = ""

    @property
    def pk(self) -> str:
        return self.id

    @property
    def full_name(self) -> str:
        return " ".join(part for part in (self.first_name, self.middle_name, self.last_name) if part)

    @property
    def label(self) -> str:
        """``Ada Lovelace (member <uuid>)``, as the import's messages name a member."""
        return f"{self.full_name or 'Unnamed member'} (member {self.id})"

    @property
    def privileged(self) -> bool:
        return self.is_staff or self.is_superuser

    @property
    def primary(self) -> EmailRecord | None:
        primaries = [email for email in self.emails if email.type == "primary"]
        return min(primaries, key=lambda email: email.created) if primaries else None

    def emails_of_type(self, email_type: str) -> list[EmailRecord]:
        return [email for email in self.emails if email.type == email_type]

    def email(self, record_id: str) -> EmailRecord | None:
        return next((email for email in self.emails if email.id == record_id), None)

    def verified_contacts(self) -> set[str]:
        """Ids of the member's verified sign-in contacts (emails and phones), as ``count_verified_recovery_contacts``."""
        return {c.id for c in self.emails if c.verified} | {p.id for p in self.phones if p.verified}


@dataclass
class Snapshot:
    """The stored records a sheet names, and their owners with every contact they have."""

    emails: dict[str, list[EmailRecord]] = field(default_factory=dict)
    phones: dict[str, PhoneRecord] = field(default_factory=dict)
    members: dict[str, MemberRecord] = field(default_factory=dict)
    uuids: dict[str, str | None] = field(default_factory=dict)
    # Live Member objects by id, for permission checks; never stored.
    objects: dict[str, Member] = field(default_factory=dict, repr=False)

    def email_records(self, address: str | None) -> list[EmailRecord]:
        return self.emails.get(address_key(address), []) if address else []

    def member(self, member_id: str | None) -> MemberRecord | None:
        return self.members.get(member_id) if member_id else None


def _comparable(value):
    if isinstance(value, dict):
        return {key: _comparable(item) for key, item in value.items() if key not in _DISPLAY_ONLY}
    if isinstance(value, list):
        return [_comparable(item) for item in value]
    return value


def fingerprint(slice_data: dict) -> str:
    """SHA-256 of a row slice's compared values, in canonical JSON."""
    canonical = json.dumps(_comparable(slice_data), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()
