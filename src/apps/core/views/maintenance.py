"""Maintenance-mode bypass endpoint."""

from collections.abc import Mapping

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import SiteMaintenanceControl


def _read_password(request) -> str:
    """Return the body's ``password``, or ``""`` when the body is not an object or holds no usable one.

    A JSON body may be any value (``null``, a list, ...) and ``password`` may be a number, list or object; both read
    as "missing" so the caller answers 400 instead of raising. A string that can never be a stored password also
    reads as missing: a lone surrogate (not UTF-8 encodable) or a NUL character (which Django's form fields reject).
    """
    data = request.data
    password = data.get("password", "") if isinstance(data, Mapping) else ""
    if not isinstance(password, str) or "\x00" in password:
        return ""
    try:
        password.encode("utf-8")
    except UnicodeEncodeError:
        return ""
    return password


class MaintenanceBypassView(APIView):
    """Verify a bypass password to skip maintenance mode."""

    permission_classes = [AllowAny]
    # The password in the body is the only credential and the view never reads the caller, so a stale Bearer token
    # (which the SPA attaches to every request) must not 401 it before the password is checked.
    authentication_classes = []

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        password = _read_password(request)
        if not password:
            return Response({"success": False, "error": "Password is required."}, status=status.HTTP_400_BAD_REQUEST)

        config = SiteMaintenanceControl.load()

        if not config.is_maintenance:
            return Response(
                {"success": False, "error": "Maintenance mode is not active."}, status=status.HTTP_400_BAD_REQUEST
            )

        if not config.bypass_password:
            return Response(
                {"success": False, "error": "Bypass is not configured."}, status=status.HTTP_400_BAD_REQUEST
            )

        if config.check_bypass_password(password):
            return Response({"success": True})

        return Response({"success": False, "error": "Incorrect password."}, status=status.HTTP_403_FORBIDDEN)
