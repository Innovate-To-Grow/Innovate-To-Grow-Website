import logging

from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from event.models import CheckIn, CheckInRecord, EventRegistration

logger = logging.getLogger(__name__)


def _ticket_type_name(registration: EventRegistration) -> str:
    """Return a resilient ticket label even if relation is missing."""
    ticket = getattr(registration, "ticket", None)
    return getattr(ticket, "name", None) or "Unknown Ticket"


def _parse_ticket_code(value: str) -> str:
    """Extract ticket_code from a barcode payload or raw ticket code."""
    value = value.strip()
    if "|" in value:
        parts = value.split("|")
        if len(parts) >= 4 and parts[0] == "I2G" and parts[1] == "EVENT":
            return parts[3]
    return value


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

        checked_in_ids = set(CheckInRecord.objects.filter(check_in=check_in).values_list("registration_id", flat=True))
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
                        "name": reg.attendee_name,
                        "email": reg.attendee_email,
                        "ticket_type": _ticket_type_name(reg),
                        "ticket_code": reg.ticket_code,
                    }
                )

        return Response(
            {
                "total": all_registrations.count(),
                "scanned": len(checked_in_ids),
                "not_checked_in": not_checked_in,
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

        attendee_info = {
            "name": registration.attendee_name,
            "email": registration.attendee_email,
            "ticket_type": _ticket_type_name(registration),
            "ticket_code": registration.ticket_code,
        }

        existing = CheckInRecord.objects.filter(check_in=check_in, registration=registration).first()
        if existing:
            return Response(
                {
                    "status": "duplicate",
                    "detail": f"Already checked in at {existing.created_at.strftime('%H:%M:%S')}",
                    "attendee": attendee_info,
                    "scanned_at": existing.created_at.isoformat(),
                }
            )

        record = CheckInRecord.objects.create(
            check_in=check_in,
            registration=registration,
            scanned_by=request.user if request.user.is_authenticated else None,
        )
        return Response(
            {
                "status": "success",
                "detail": "Checked in successfully.",
                "attendee": attendee_info,
                "scanned_at": record.created_at.isoformat(),
                "scan_count": check_in.records.count(),
            },
            status=status.HTTP_201_CREATED,
        )
