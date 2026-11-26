"""Loading what the database holds for a sheet, in chunks, and storing a review's slice of it with the batch."""

from __future__ import annotations

from dataclasses import asdict, fields

from django.db.models.functions import Upper

from apps.authn.models import ContactEmail, ContactPhone, Member

from .records import EmailRecord, MemberRecord, PhoneRecord, Snapshot, address_key, us_phone

CHUNK = 500


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


def _record(cls, values: dict):
    """``cls(**values)``, without the keys ``cls`` no longer has: a slice stored by an older release (for example a
    member's ``is_superuser``) still loads."""
    known = {item.name for item in fields(cls)}
    return cls(**{key: value for key, value in values.items() if key in known})


def snapshot_from_slice(data: dict) -> Snapshot:
    """Rebuild the snapshot a row's analysis read from its stored slice."""
    members = {}
    for member_id, values in (data.get("members") or {}).items():
        record = dict(values)
        record["emails"] = [_record(EmailRecord, email) for email in record.get("emails", [])]
        record["phones"] = [_record(PhoneRecord, phone) for phone in record.get("phones", [])]
        members[member_id] = _record(MemberRecord, record)
    return Snapshot(
        emails={key: [_record(EmailRecord, c) for c in records] for key, records in (data.get("emails") or {}).items()},
        phones={key: _record(PhoneRecord, value) for key, value in (data.get("phones") or {}).items() if value},
        members=members,
        uuids=dict(data.get("uuids") or {}),
    )
