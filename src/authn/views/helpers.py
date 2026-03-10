"""
Shared helpers for auth API responses.
"""

from rest_framework import status
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from authn.services import AuthChallengeDeliveryError, AuthChallengeThrottled


def build_auth_success_payload(member, message: str) -> dict:
    refresh = RefreshToken.for_user(member)
    return {
        "message": message,
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": {
            "member_uuid": str(member.member_uuid),
            "email": member.email,
            "username": member.username,
            "display_name": member.get_full_name() or member.username,
        },
    }


def challenge_error_response(exc: Exception) -> Response:
    if isinstance(exc, AuthChallengeThrottled):
        return Response({"detail": str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    if isinstance(exc, AuthChallengeDeliveryError):
        return Response({"detail": "Failed to send verification email."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    raise exc
