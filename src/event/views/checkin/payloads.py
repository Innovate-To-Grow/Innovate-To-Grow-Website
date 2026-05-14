from rest_framework.response import Response

from event.models import CheckIn, CheckInRecord, EventRegistration


def ticket_type_name(registration: EventRegistration) -> str:
    ticket = getattr(registration, "ticket", None)
    return getattr(ticket, "name", None) or "Unknown Ticket"


def parse_ticket_code(value: str) -> str:
    import event.views.checkin as checkin_api

    value = str(value or "").strip()
    compact_value = checkin_api.re.sub(r"\s+", "", value)
    match = checkin_api.TICKET_CODE_RE.search(compact_value)
    if match:
        return match.group(0).upper()
    if "|" in compact_value:
        parts = compact_value.split("|")
        if len(parts) >= 4 and parts[0] == "I2G" and parts[1] == "EVENT":
            return parts[3]
    return value


def attendee_payload(registration: EventRegistration) -> dict:
    return {
        "id": str(registration.pk),
        "name": registration.attendee_name,
        "email": registration.attendee_email,
        "organization": registration.attendee_organization or "",
        "ticket_type": ticket_type_name(registration),
        "ticket_code": registration.ticket_code,
    }


def registration_status_payload(registration: EventRegistration, record: CheckInRecord | None = None) -> dict:
    member = getattr(registration, "member", None)
    payload = attendee_payload(registration)
    payload.update(
        {
            "member_organization": getattr(member, "organization", "") or "",
            "member_title": getattr(member, "title", "") or "",
            "checked_in": record is not None,
            "checked_in_at": record.created_at.isoformat() if record else "",
            "checked_in_station": record.check_in.name if record else "",
            "check_in_record_id": str(record.pk) if record else "",
        }
    )
    return payload


def check_in_payload(check_in: CheckIn) -> dict:
    return {
        "id": str(check_in.pk),
        "name": check_in.name,
        "event": {
            "id": str(check_in.event_id),
            "name": check_in.event.name,
        },
        "is_active": check_in.is_active,
    }


def record_payload(record: CheckInRecord) -> dict:
    scanned_by = record.scanned_by.get_full_name() if record.scanned_by_id and record.scanned_by else ""
    return {
        "id": str(record.pk),
        "attendee": attendee_payload(record.registration),
        "check_in": check_in_payload(record.check_in),
        "scanned_by": scanned_by,
        "scanned_at": record.created_at.isoformat(),
    }


def event_counts(check_in: CheckIn) -> dict:
    registrations = EventRegistration.objects.filter(event=check_in.event)
    event_checked_in = CheckInRecord.objects.filter(registration__event=check_in.event)
    station_checked_in = CheckInRecord.objects.filter(check_in=check_in)
    return {
        "total": registrations.count(),
        "scanned": event_checked_in.count(),
        "station_scanned": station_checked_in.count(),
    }


def duplicate_response(
    record: CheckInRecord,
    attempted_check_in: CheckIn | None = None,
):
    station = attempted_check_in or record.check_in
    return Response(
        {
            "status": "duplicate",
            "detail": f"Already checked in at {record.created_at.strftime('%H:%M:%S')}",
            "attendee": attendee_payload(record.registration),
            "record_id": str(record.pk),
            "scanned_at": record.created_at.isoformat(),
            "existing_check_in": check_in_payload(record.check_in),
            "station_scan_count": station.records.count(),
        }
    )
