"""Maintenance-mode bypass endpoint."""

from collections.abc import Mapping

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import SiteMaintenanceControl
from apps.core.services.request_limits.view_limits import failure_lockout, record_failure

# Wrong passwords from everyone together, per period (the live "view-maintenance-bypass" request-limit policy):
# there is one shared password, so there is one shared lockout, never a per-IP one (the campus shares an address).
BYPASS_FAILURES = "view-maintenance-bypass"


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


def _locked_response(seconds: int) -> Response:
    response = Response(
        {
            "success": False,
            "error": "Too many incorrect passwords. Please try again later.",
            "code": "rate_limited",
            "retry_after": seconds,
        },
        status=status.HTTP_429_TOO_MANY_REQUESTS,
    )
    response["Retry-After"] = str(seconds)
    return response


class MaintenanceBypassView(APIView):
    """Verify a bypass password to skip maintenance mode.

    After too many wrong passwords in a period every attempt is refused (429) until the period ends, a correct one
    included, and before any password is hashed, so the password cannot be brute-forced.
    """

    permission_classes = [AllowAny]
    rate_limit_scope = "auth-sign-in"
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

        locked = failure_lockout(BYPASS_FAILURES)
        if locked is not None:
            return _locked_response(locked)

        if config.check_bypass_password(password):
            return Response({"success": True})

        record_failure(BYPASS_FAILURES)
        return Response({"success": False, "error": "Incorrect password."}, status=status.HTTP_403_FORBIDDEN)
