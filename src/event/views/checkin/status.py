from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from event.models import CheckIn, CheckInRecord, EventRegistration

from .payloads import attendee_payload, check_in_payload, event_counts, record_payload, registration_status_payload


class CheckInStatusView(APIView):
    """Returns check-in stats and a not-yet-checked-in list."""

    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminUser]

    # noinspection PyMethodMayBeStatic
    def get(self, request, checkin_id):
        try:
            check_in = CheckIn.objects.select_related("event").get(pk=checkin_id)
        except CheckIn.DoesNotExist:
            return Response(
                {"detail": "Check-in session not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        check_in_records = (
            CheckInRecord.objects.filter(registration__event=check_in.event)
            .select_related("check_in")
            .order_by("-created_at")
        )
        record_by_registration = {record.registration_id: record for record in check_in_records}
        all_registrations = (
            EventRegistration.objects.filter(event=check_in.event)
            .select_related("ticket", "member")
            .order_by("attendee_first_name", "attendee_last_name")
        )
        registration_statuses = [
            registration_status_payload(registration, record_by_registration.get(registration.pk))
            for registration in all_registrations
        ]
        recent_scans = (
            CheckInRecord.objects.filter(check_in=check_in)
            .select_related(
                "check_in",
                "check_in__event",
                "registration",
                "registration__ticket",
                "scanned_by",
            )
            .order_by("-created_at")[:25]
        )
        counts = event_counts(check_in)
        return Response(
            {
                "check_in": check_in_payload(check_in),
                "total": counts["total"],
                "scanned": counts["scanned"],
                "station_scanned": counts["station_scanned"],
                "not_checked_in": [
                    attendee_payload(registration)
                    for registration in all_registrations
                    if registration.pk not in record_by_registration
                ],
                "registrations": registration_statuses,
                "recent_scans": [record_payload(record) for record in recent_scans],
            }
        )
