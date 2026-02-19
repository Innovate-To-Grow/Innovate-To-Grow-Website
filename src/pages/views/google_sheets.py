import logging

from django.shortcuts import get_object_or_404
from googleapiclient.errors import HttpError
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import GoogleSheet
from ..services import GoogleSheetsConfigError, fetch_sheet_values

logger = logging.getLogger(__name__)


class GoogleSheetDataView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, sheet_id, *args, **kwargs):
        sheet = get_object_or_404(GoogleSheet, pk=sheet_id, is_enabled=True)

        try:
            data = fetch_sheet_values(sheet)
        except GoogleSheetsConfigError:
            logger.exception("Google Sheets configuration error while loading sheet %s.", sheet_id)
            return Response(
                {"detail": "Google Sheets is not configured."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except HttpError:
            logger.exception("Google Sheets API error while loading sheet %s.", sheet_id)
            return Response(
                {"detail": "Failed to fetch Google Sheet data."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(
            {
                "sheet_id": str(sheet.id),
                "sheet_name": sheet.sheet_name,
                "headers": data["headers"],
                "rows": data["rows"],
            }
        )
