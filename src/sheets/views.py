import logging

from django.core.cache import cache
from googleapiclient.errors import HttpError
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import GoogleSheetSource
from .services import GoogleSheetsConfigError, fetch_source_data

logger = logging.getLogger(__name__)


class SheetsDataView(APIView):
    """Public endpoint to retrieve cached Google Sheets data by slug."""

    permission_classes = [AllowAny]

    def get(self, request, slug):
        try:
            source = GoogleSheetSource.objects.get(slug=slug, is_active=True)
        except GoogleSheetSource.DoesNotExist:
            return Response({"detail": "Sheet source not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            data = fetch_source_data(source)
        except GoogleSheetsConfigError as exc:
            logger.error("Google Sheets config error for '%s': %s", slug, exc)
            return Response(
                {"detail": "Google Sheets service is not configured."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except HttpError as exc:
            logger.error("Google Sheets API error for '%s': %s", slug, exc)
            return Response(
                {"detail": "Failed to fetch data from Google Sheets."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Unexpected error fetching sheet '%s': %s", slug, exc)
            return Response(
                {"detail": "Failed to fetch data from Google Sheets."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(data)


class SheetsRefreshView(APIView):
    """Admin-only endpoint to force-refresh cached sheet data."""

    permission_classes = [IsAdminUser]

    def post(self, request, slug):
        try:
            source = GoogleSheetSource.objects.get(slug=slug)
        except GoogleSheetSource.DoesNotExist:
            return Response({"detail": "Sheet source not found."}, status=status.HTTP_404_NOT_FOUND)

        cache.delete(f"sheets:{source.slug}:data")
        cache.delete(f"sheets:{source.slug}:stale")
        cache.delete("layout:data")

        try:
            data = fetch_source_data(source)
        except GoogleSheetsConfigError as exc:
            logger.error("Google Sheets config error for '%s': %s", slug, exc)
            return Response(
                {"detail": "Google Sheets service is not configured."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except HttpError as exc:
            logger.error("Google Sheets API error for '%s': %s", slug, exc)
            return Response(
                {"detail": "Failed to fetch data from Google Sheets."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Unexpected error refreshing sheet '%s': %s", slug, exc)
            return Response(
                {"detail": "Failed to fetch data from Google Sheets."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(data)
