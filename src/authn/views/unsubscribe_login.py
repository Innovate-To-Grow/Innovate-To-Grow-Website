"""
Auto-login view for email unsubscribe / preference management.
"""

import logging

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from authn.services.unsubscribe_token import get_member_from_unsubscribe_token
from authn.views.helpers import build_auth_success_payload

logger = logging.getLogger(__name__)


class UnsubscribeAutoLoginView(APIView):
    """Exchange a signed unsubscribe-email token for JWT credentials."""

    permission_classes = [AllowAny]

    def post(self, request):
        token = request.data.get("token", "").strip()
        if not token:
            return Response({"detail": "Token is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            member = get_member_from_unsubscribe_token(token)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        payload = build_auth_success_payload(member, "Login successful.")
        return Response(payload, status=status.HTTP_200_OK)
