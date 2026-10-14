"""
Login view for user authentication.
"""

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authn.serializers import LoginSerializer
from apps.authn.services import login_guard

from ..helpers import build_auth_success_payload


def _locked_response(retry_after: int) -> Response:
    response = Response(
        {"detail": login_guard.LOCKED_DETAIL, "code": login_guard.LOCKED_CODE},
        status=status.HTTP_429_TOO_MANY_REQUESTS,
    )
    response["Retry-After"] = str(retry_after)
    return response


class LoginView(APIView):
    """
    API endpoint for user login.
    Returns JWT access and refresh tokens.

    No per-IP throttle by design (campus users share one public IP). Password guessing is bounded per identifier
    by ``login_guard``: too many recent failures answer 429 ``login_locked`` before the password is even checked.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        serializer = LoginSerializer(data=request.data)

        try:
            is_valid = serializer.is_valid()
        except login_guard.LoginLocked as exc:
            return _locked_response(exc.retry_after)

        if not is_valid:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.validated_data["user"]

        return Response(
            build_auth_success_payload(user, "Login successful."),
            status=status.HTTP_200_OK,
        )
