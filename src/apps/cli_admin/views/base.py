from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.http import Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.services.db_tools.safe_orm import ActionRequestError

from ..authentication import CliTokenAuthentication
from ..permissions import IsActiveStaff
from ..services.crud import StaleSnapshotError


def _error_detail(exc):
    if isinstance(exc, DjangoValidationError):
        return exc.messages
    return str(exc)


class AdminAPIView(APIView):
    """Base for the /admin-api/ resource views.

    Pins CLI bearer auth + the active-staff gate (so the global SimpleJWT default
    never applies here) and maps the shared safe-ORM exceptions to HTTP statuses.
    """

    authentication_classes = [CliTokenAuthentication]
    permission_classes = [IsActiveStaff]

    def handle_exception(self, exc):
        if isinstance(exc, StaleSnapshotError):
            return Response({"error": "conflict", "detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        if isinstance(exc, IntegrityError):
            return Response(
                {"error": "conflict", "detail": "Database integrity error."}, status=status.HTTP_409_CONFLICT
            )
        if isinstance(exc, (ActionRequestError, DjangoValidationError)):
            return Response({"error": "bad_request", "detail": _error_detail(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if isinstance(exc, (Http404, ObjectDoesNotExist)):
            return Response(
                {"error": "not_found", "detail": str(exc) or "Not found."}, status=status.HTTP_404_NOT_FOUND
            )
        return super().handle_exception(exc)
