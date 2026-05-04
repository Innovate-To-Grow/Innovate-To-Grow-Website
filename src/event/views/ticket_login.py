import logging

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from authn.views.helpers import build_auth_success_payload
from event.services.ticket_assets import (
    TicketLoginTokenError,
    get_member_from_login_token,
)

logger = logging.getLogger(__name__)


class TicketAutoLoginView(APIView):
    """Exchange a signed ticket-email token for JWT credentials."""

    permission_classes = [AllowAny]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        token = request.data.get("token", "").strip()
        if not token:
            return Response({"detail": "Token is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            member = get_member_from_login_token(token)
        except TicketLoginTokenError:
            return Response({"detail": "Invalid or expired ticket login link."}, status=status.HTTP_400_BAD_REQUEST)

        payload = build_auth_success_payload(member, "Login successful.")
        return Response(payload, status=status.HTTP_200_OK)
