"""What the database holds for the addresses, numbers and Member UUIDs a sheet names.

The lookups run a fixed number of queries per chunk of the sheet, whatever its size. Addresses are matched ignoring
case through ``UPPER()``, the comparison Django's ``iexact`` makes on PostgreSQL, and are keyed in memory by
``upper().lower()`` as ``login_guard.normalize_identifier`` does, so the database and this code agree on which
addresses are the same. The unique constraint on ``ContactEmail.email_address`` is case-sensitive, so one key can hold
several records: legacy duplicates that differ only in letter case.

A row's analysis reads only its own part of the snapshot (``row_slice``). That part is stored on the row, so the review
page can show it, and its SHA-256 (``fingerprint``) is what the apply compares to find records that changed after the
review. The fingerprint hashes values, not ``updated_at``: queryset ``.update()`` calls such as the Contact Emails
"Mark verified" action don't touch ``auto_now``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

from django.db.models.functions import Upper

from apps.authn.models import ContactEmail, ContactPhone, Member

from ..contacts import phone_parts

CHUNK = 500
# Shown on the review page, never compared: a member signing in must not send an import back to review.
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


def _chunks(values):
    values = sorted(values)
    for start in range(0, len(values), CHUNK):
        yield values[start : start + CHUNK]


def _email_record(contact: ContactEmail) -> EmailRecord:
    return EmailRecord(
        id=str(contact.pk),
        address=contact.email_address,
        type=contact.email_type,
        member=str(contact.member_id) if contact.member_id else None,
        verified=contact.verified,
        subscribe=contact.subscribe,
        created=contact.created_at.isoformat() if contact.created_at else "",
    )


def _phone_record(phone: ContactPhone) -> PhoneRecord:
    return PhoneRecord(
        id=str(phone.pk),
        number=phone.phone_number,
        region=phone.region,
        member=str(phone.member_id) if phone.member_id else None,
        verified=phone.verified,
        subscribe=phone.subscribe,
        created=phone.created_at.isoformat() if phone.created_at else "",
    )


def _member_record(member: Member) -> MemberRecord:
    return MemberRecord(
        id=str(member.pk),
        first_name=member.first_name or "",
        middle_name=member.middle_name or "",
        last_name=member.last_name or "",
        organization=member.organization or "",
        title=member.title or "",
        is_active=member.is_active,
        is_staff=member.is_staff,
        is_superuser=member.is_superuser,
        registration_pending=member.registration_pending,
        emails=sorted((_email_record(c) for c in member.contact_emails.all()), key=lambda c: c.id),
        phones=sorted((_phone_record(p) for p in member.contact_phones.all()), key=lambda p: p.id),
        date_joined=member.date_joined.isoformat() if member.date_joined else "",
        last_login=member.last_login.isoformat() if member.last_login else "",
    )


def load_snapshot(rows: list[dict]) -> Snapshot:
    """Read every record the parsed ``rows`` name: their addresses, US phone numbers and Member UUIDs."""
    snapshot = Snapshot()
    keys = {address_key(row[name]) for row in rows for name in ("primary_email", "secondary_email") if row.get(name)}
    for chunk in _chunks(keys):
        uppers = [key.upper() for key in chunk]
        query = ContactEmail.objects.annotate(_upper=Upper("email_address")).filter(_upper__in=uppers)
        for contact in query.order_by("created_at", "pk"):
            snapshot.emails.setdefault(address_key(contact.email_address), []).append(_email_record(contact))
    numbers = {phone[0] for row in rows if (phone := us_phone(row.get("phone_number")))}
    for chunk in _chunks(numbers):
        for phone in ContactPhone.objects.filter(phone_number__in=chunk):
            snapshot.phones[phone.phone_number] = _phone_record(phone)
    uuids = {row["member_uuid"] for row in rows if row.get("member_uuid")}
    found = set()
    for chunk in _chunks(uuids):
        found.update(str(pk) for pk in Member.objects.filter(pk__in=chunk).values_list("pk", flat=True))
    snapshot.uuids = {value: (value if value in found else None) for value in uuids}
    owners = {c.member for records in snapshot.emails.values() for c in records if c.member}
    owners |= {p.member for p in snapshot.phones.values() if p.member} | found
    for chunk in _chunks(owners):
        query = Member.objects.filter(pk__in=chunk).defer("profile_image", "password")
        for member in query.prefetch_related("contact_emails", "contact_phones"):
            snapshot.members[str(member.pk)] = _member_record(member)
            snapshot.objects[str(member.pk)] = member
    return snapshot


def row_slice(snapshot: Snapshot, row: dict) -> dict:
    """The part of ``snapshot`` that ``row``'s analysis reads, as JSON: its records and their owners."""
    keys = sorted({address_key(row[name]) for name in ("primary_email", "secondary_email") if row.get(name)})
    emails = {key: [asdict(record) for record in snapshot.emails.get(key, [])] for key in keys}
    phone = us_phone(row.get("phone_number"))
    phones = {}
    if phone:
        record = snapshot.phones.get(phone[0])
        phones[phone[0]] = asdict(record) if record else None
    uuids = {row["member_uuid"]: snapshot.uuids.get(row["member_uuid"])} if row.get("member_uuid") else {}
    owners = {c["member"] for records in emails.values() for c in records if c["member"]}
    owners |= {p["member"] for p in phones.values() if p and p["member"]}
    owners |= {value for value in uuids.values() if value}
    members = {member_id: asdict(snapshot.members[member_id]) for member_id in sorted(owners)}
    return {"emails": emails, "phones": phones, "uuids": uuids, "members": members}


def snapshot_from_slice(data: dict) -> Snapshot:
    """Rebuild the snapshot a row's analysis read from its stored slice."""
    members = {}
    for member_id, values in (data.get("members") or {}).items():
        record = dict(values)
        record["emails"] = [EmailRecord(**email) for email in record.get("emails", [])]
        record["phones"] = [PhoneRecord(**phone) for phone in record.get("phones", [])]
        members[member_id] = MemberRecord(**record)
    return Snapshot(
        emails={key: [EmailRecord(**c) for c in records] for key, records in (data.get("emails") or {}).items()},
        phones={key: PhoneRecord(**value) for key, value in (data.get("phones") or {}).items() if value},
        members=members,
        uuids=dict(data.get("uuids") or {}),
    )


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
