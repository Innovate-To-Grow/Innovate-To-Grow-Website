"""Logout view — blacklists the supplied refresh token."""

import logging
from collections.abc import Mapping

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

logger = logging.getLogger(__name__)


class LogoutView(APIView):
    """Blacklist the caller's refresh token so it can no longer be used.

    Runs no authentication (the refresh token in the body is the credential), so an expired or otherwise
    invalid access token can't block logout.
    """

    permission_classes = [AllowAny]
    # Authenticated by the refresh token in the body: a stale, expired or other-account Bearer must never 401 this.
    authentication_classes = []

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        # A JSON body may be any value (null, a list, ...); only an object can carry the refresh token.
        data = request.data
        refresh = data.get("refresh", "") if isinstance(data, Mapping) else ""
        if not isinstance(refresh, str) or not refresh.strip():
            return Response({"detail": "Refresh token is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            RefreshToken(refresh).blacklist()
        except (TokenError, UnicodeEncodeError):  # the latter: a lone surrogate can't be decoded as a JWT at all
            return Response({"detail": "Invalid or already-blacklisted token."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)
