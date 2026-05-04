import logging
import re

from django.db import IntegrityError
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from event.models import CheckIn, CheckInRecord, EventRegistration

logger = logging.getLogger(__name__)
TICKET_CODE_RE = re.compile(r"\bI2G-[A-F0-9]{12}\b", re.IGNORECASE)


def _ticket_type_name(registration: EventRegistration) -> str:
    """Return a resilient ticket label even if relation is missing."""
    ticket = getattr(registration, "ticket", None)
    return getattr(ticket, "name", None) or "Unknown Ticket"


def _parse_ticket_code(value: str) -> str:
    """Extract ticket_code from a barcode payload or raw ticket code."""
    value = str(value or "").strip()
    compact_value = re.sub(r"\s+", "", value)
    match = TICKET_CODE_RE.search(compact_value)
    if match:
        return match.group(0).upper()
    if "|" in compact_value:
        parts = compact_value.split("|")
        if len(parts) >= 4 and parts[0] == "I2G" and parts[1] == "EVENT":
            return parts[3]
    return value


def _attendee_payload(registration: EventRegistration) -> dict:
    return {
        "id": str(registration.pk),
        "name": registration.attendee_name,
        "email": registration.attendee_email,
        "organization": registration.attendee_organization or "",
        "ticket_type": _ticket_type_name(registration),
        "ticket_code": registration.ticket_code,
    }


def _check_in_payload(check_in: CheckIn) -> dict:
    return {
        "id": str(check_in.pk),
        "name": check_in.name,
        "event": {
            "id": str(check_in.event_id),
            "name": check_in.event.name,
        },
        "is_active": check_in.is_active,
    }


def _record_payload(record: CheckInRecord) -> dict:
    scanned_by = record.scanned_by.get_full_name() if record.scanned_by_id and record.scanned_by else ""
    return {
        "id": str(record.pk),
        "attendee": _attendee_payload(record.registration),
        "check_in": _check_in_payload(record.check_in),
        "scanned_by": scanned_by,
        "scanned_at": record.created_at.isoformat(),
    }


def _event_counts(check_in: CheckIn) -> dict:
    registrations = EventRegistration.objects.filter(event=check_in.event)
    event_checked_in = CheckInRecord.objects.filter(registration__event=check_in.event)
    station_checked_in = CheckInRecord.objects.filter(check_in=check_in)
    return {
        "total": registrations.count(),
        "scanned": event_checked_in.count(),
        "station_scanned": station_checked_in.count(),
    }


def _duplicate_response(record: CheckInRecord, attempted_check_in: CheckIn | None = None):
    station = attempted_check_in or record.check_in
    return Response(
        {
            "status": "duplicate",
            "detail": f"Already checked in at {record.created_at.strftime('%H:%M:%S')}",
            "attendee": _attendee_payload(record.registration),
            "record_id": str(record.pk),
            "scanned_at": record.created_at.isoformat(),
            "existing_check_in": _check_in_payload(record.check_in),
            "station_scan_count": station.records.count(),
        }
    )


class CheckInStatusView(APIView):
    """Returns check-in stats: scanned count, total registrations, and not-yet-checked-in list."""

    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminUser]

    # noinspection PyMethodMayBeStatic
    def get(self, request, checkin_id):
        try:
            check_in = CheckIn.objects.select_related("event").get(pk=checkin_id)
        except CheckIn.DoesNotExist:
            return Response({"detail": "Check-in session not found."}, status=status.HTTP_404_NOT_FOUND)

        checked_in_ids = set(
            CheckInRecord.objects.filter(registration__event=check_in.event).values_list("registration_id", flat=True)
        )
        all_registrations = (
            EventRegistration.objects.filter(event=check_in.event)
            .select_related("ticket")
            .order_by("attendee_first_name", "attendee_last_name")
        )

        not_checked_in = []
        for reg in all_registrations:
            if reg.pk not in checked_in_ids:
                not_checked_in.append(
                    {
                        **_attendee_payload(reg),
                    }
                )

        recent_scans = (
            CheckInRecord.objects.filter(check_in=check_in)
            .select_related("check_in", "check_in__event", "registration", "registration__ticket", "scanned_by")
            .order_by("-created_at")[:25]
        )
        counts = _event_counts(check_in)
        return Response(
            {
                "check_in": _check_in_payload(check_in),
                "total": counts["total"],
                "scanned": counts["scanned"],
                "station_scanned": counts["station_scanned"],
                "not_checked_in": not_checked_in,
                "recent_scans": [_record_payload(record) for record in recent_scans],
            }
        )


class CheckInScanView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminUser]

    # noinspection PyMethodMayBeStatic
    def post(self, request, checkin_id):
        try:
            check_in = CheckIn.objects.select_related("event").get(pk=checkin_id)
        except CheckIn.DoesNotExist:
            return Response(
                {"status": "error", "detail": "Check-in session not found."}, status=status.HTTP_404_NOT_FOUND
            )

        if not check_in.is_active:
            return Response(
                {"status": "error", "detail": "This check-in session is not active."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        raw = request.data.get("barcode", "") or request.data.get("ticket_code", "")
        if not raw:
            return Response(
                {"status": "error", "detail": "Barcode or ticket code is required."}, status=status.HTTP_400_BAD_REQUEST
            )

        ticket_code = _parse_ticket_code(raw)

        registration = (
            EventRegistration.objects.filter(ticket_code=ticket_code, event=check_in.event)
            .select_related("ticket")
            .first()
        )
        if registration is None:
            return Response(
                {
                    "status": "not_found",
                    "detail": f"No registration found for code: {ticket_code}",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            record, created = CheckInRecord.objects.select_related(
                "check_in", "check_in__event", "registration", "registration__ticket", "scanned_by"
            ).get_or_create(
                registration=registration,
                defaults={
                    "check_in": check_in,
                    "scanned_by": request.user if request.user.is_authenticated else None,
                },
            )
        except IntegrityError:
            record = (
                CheckInRecord.objects.filter(registration=registration)
                .select_related("check_in", "check_in__event", "registration", "registration__ticket", "scanned_by")
                .first()
            )
            if record:
                return _duplicate_response(record, check_in)
            logger.exception("Check-in unique constraint conflict without a persisted record")
            return Response(
                {"status": "error", "detail": "Could not finalize check-in. Please try again."},
                status=status.HTTP_409_CONFLICT,
            )

        if not created:
            return _duplicate_response(record, check_in)

        record = (
            CheckInRecord.objects.select_related("check_in", "check_in__event", "registration", "registration__ticket")
            .filter(pk=record.pk)
            .get()
        )
        return Response(
            {
                "status": "success",
                "detail": "Checked in successfully.",
                "attendee": _attendee_payload(registration),
                "record_id": str(record.pk),
                "scanned_at": record.created_at.isoformat(),
                "scan_count": CheckInRecord.objects.filter(registration__event=check_in.event).count(),
                "station_scan_count": check_in.records.count(),
                "existing_check_in": None,
            },
            status=status.HTTP_201_CREATED,
        )


class CheckInUndoView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminUser]

    # noinspection PyMethodMayBeStatic
    def post(self, request, checkin_id, record_id):
        try:
            check_in = CheckIn.objects.select_related("event").get(pk=checkin_id)
        except CheckIn.DoesNotExist:
            return Response(
                {"status": "error", "detail": "Check-in session not found."}, status=status.HTTP_404_NOT_FOUND
            )

        record = CheckInRecord.objects.filter(pk=record_id, check_in=check_in).first()
        if record is None:
            return Response(
                {"status": "error", "detail": "Check-in record not found for this station."},
                status=status.HTTP_404_NOT_FOUND,
            )

        record.delete()
        counts = _event_counts(check_in)
        return Response(
            {
                "status": "removed",
                "record_id": str(record_id),
                "scanned": counts["scanned"],
                "station_scanned": counts["station_scanned"],
            }
        )
