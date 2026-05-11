from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from event.models import CheckIn, CheckInRecord

from .payloads import event_counts


class CheckInUndoView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAdminUser]

    # noinspection PyMethodMayBeStatic
    def post(self, request, checkin_id, record_id):
        try:
            check_in = CheckIn.objects.select_related("event").get(pk=checkin_id)
        except CheckIn.DoesNotExist:
            return Response(
                {"status": "error", "detail": "Check-in session not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        record = CheckInRecord.objects.filter(pk=record_id, check_in=check_in).first()
        if record is None:
            return Response(
                {
                    "status": "error",
                    "detail": "Check-in record not found for this station.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        record.delete()
        counts = event_counts(check_in)
        return Response(
            {
                "status": "removed",
                "record_id": str(record_id),
                "scanned": counts["scanned"],
                "station_scanned": counts["station_scanned"],
            }
        )
