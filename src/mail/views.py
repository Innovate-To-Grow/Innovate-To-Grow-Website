import logging

from django.http import HttpResponse
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from authn.views.helpers import build_auth_success_payload

from .login_redirects import get_magic_login_redirect_path
from .models import MagicLoginToken
from .services.unsubscribe_token import get_member_from_oneclick_token

logger = logging.getLogger(__name__)


class MagicLoginView(APIView):
    """Exchange a campaign login token for JWT credentials."""

    permission_classes = [AllowAny]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        token = request.data.get("token", "").strip()
        if not token:
            return Response({"detail": "Token is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            magic = MagicLoginToken.objects.select_related("member", "campaign").get(token=token)
        except MagicLoginToken.DoesNotExist:
            return Response({"detail": "Invalid login link."}, status=status.HTTP_400_BAD_REQUEST)

        if not magic.is_valid:
            return Response({"detail": "This login link has expired."}, status=status.HTTP_400_BAD_REQUEST)
        payload = build_auth_success_payload(magic.member, "Login successful.")
        payload["redirect_to"] = get_magic_login_redirect_path(magic.campaign)
        return Response(payload, status=status.HTTP_200_OK)


class OneClickUnsubscribeView(APIView):
    """RFC 8058 one-click unsubscribe endpoint.

    Email clients POST to this URL to unsubscribe a user from newsletters.
    The token in the URL path identifies the member via a signed payload.
    """

    permission_classes = [AllowAny]
    http_method_names = ["post"]

    # noinspection PyMethodMayBeStatic
    def post(self, request, token):
        try:
            member = get_member_from_oneclick_token(token)
        except ValueError as exc:
            return HttpResponse(str(exc), status=400, content_type="text/plain")

        member.email_subscribe = False
        member.save(update_fields=["email_subscribe"])
        return HttpResponse("Unsubscribed successfully.", status=200, content_type="text/plain")
