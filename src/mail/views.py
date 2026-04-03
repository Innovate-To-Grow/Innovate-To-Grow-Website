import logging

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from authn.views.helpers import build_auth_success_payload

from .models import MagicLoginToken

logger = logging.getLogger(__name__)


class MagicLoginView(APIView):
    """Exchange a one-time campaign login token for JWT credentials."""

    permission_classes = [AllowAny]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        token = request.data.get("token", "").strip()
        if not token:
            return Response({"detail": "Token is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            magic = MagicLoginToken.objects.select_related("member").get(token=token)
        except MagicLoginToken.DoesNotExist:
            return Response({"detail": "Invalid login link."}, status=status.HTTP_400_BAD_REQUEST)

        if not magic.is_valid:
            reason = "This login link has already been used." if magic.is_used else "This login link has expired."
            return Response({"detail": reason}, status=status.HTTP_400_BAD_REQUEST)

        magic.consume()
        payload = build_auth_success_payload(magic.member, "Login successful.")
        return Response(payload, status=status.HTTP_200_OK)
