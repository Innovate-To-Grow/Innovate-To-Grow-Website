from django.db import IntegrityError
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from event.models import CheckIn, CheckInRecord, EventRegistration

from .payloads import attendee_payload, duplicate_response, parse_ticket_code


class CheckInScanView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminUser]

    # noinspection PyMethodMayBeStatic
    def post(self, request, checkin_id):
        check_in_response = _get_active_check_in(checkin_id)
        if isinstance(check_in_response, Response):
            return check_in_response
        check_in = check_in_response

        raw = request.data.get("barcode", "") or request.data.get("ticket_code", "")
        if not raw:
            return Response(
                {"status": "error", "detail": "Barcode or ticket code is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ticket_code = parse_ticket_code(raw)
        registration = _find_registration(check_in, ticket_code)
        if registration is None:
            return Response(
                {
                    "status": "not_found",
                    "detail": f"No registration found for code: {ticket_code}",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        record_response = _create_check_in_record(request, check_in, registration)
        if isinstance(record_response, Response):
            return record_response
        record = record_response

        return Response(
            {
                "status": "success",
                "detail": "Checked in successfully.",
                "attendee": attendee_payload(registration),
                "record_id": str(record.pk),
                "scanned_at": record.created_at.isoformat(),
                "scan_count": CheckInRecord.objects.filter(registration__event=check_in.event).count(),
                "station_scan_count": check_in.records.count(),
                "existing_check_in": None,
            },
            status=status.HTTP_201_CREATED,
        )


def _get_active_check_in(checkin_id):
    try:
        check_in = CheckIn.objects.select_related("event").get(pk=checkin_id)
    except CheckIn.DoesNotExist:
        return Response(
            {"status": "error", "detail": "Check-in session not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if not check_in.is_active:
        return Response(
            {"status": "error", "detail": "This check-in session is not active."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return check_in


def _find_registration(check_in: CheckIn, ticket_code: str):
    return (
        EventRegistration.objects.filter(ticket_code=ticket_code, event=check_in.event).select_related("ticket").first()
    )


def _create_check_in_record(request, check_in: CheckIn, registration: EventRegistration):
    import event.views.checkin as checkin_api

    try:
        record, created = CheckInRecord.objects.select_related(
            "check_in",
            "check_in__event",
            "registration",
            "registration__ticket",
            "scanned_by",
        ).get_or_create(
            registration=registration,
            defaults={
                "check_in": check_in,
                "scanned_by": request.user if request.user.is_authenticated else None,
            },
        )
    except IntegrityError:
        record = _existing_record(registration)
        if record:
            return duplicate_response(record, check_in)
        checkin_api.logger.exception("Check-in unique constraint conflict without a persisted record")
        return Response(
            {"status": "error", "detail": "Could not finalize check-in. Please try again."},
            status=status.HTTP_409_CONFLICT,
        )

    if not created:
        return duplicate_response(record, check_in)
    return _reload_record(record)


def _existing_record(registration: EventRegistration):
    return (
        CheckInRecord.objects.filter(registration=registration)
        .select_related(
            "check_in",
            "check_in__event",
            "registration",
            "registration__ticket",
            "scanned_by",
        )
        .first()
    )


def _reload_record(record):
    return (
        CheckInRecord.objects.select_related(
            "check_in",
            "check_in__event",
            "registration",
            "registration__ticket",
        )
        .filter(pk=record.pk)
        .get()
    )
