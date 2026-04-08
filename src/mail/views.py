import logging

from django.conf import settings
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
    """Unsubscribe endpoint.

    - **POST** (RFC 8058): email clients call this automatically.
    - **GET**: users click the visible link in the email footer and
      are immediately unsubscribed with a confirmation HTML page.
    """

    permission_classes = [AllowAny]
    http_method_names = ["get", "post"]

    def _unsubscribe(self, token):
        """Validate *token*, opt the member out, and return the member or an error string."""
        try:
            member = get_member_from_oneclick_token(token)
        except ValueError as exc:
            return str(exc)

        if member.email_subscribe:
            member.email_subscribe = False
            member.save(update_fields=["email_subscribe"])
            _send_unsubscribe_confirmation(member)

        return member

    # noinspection PyMethodMayBeStatic
    def get(self, request, token):
        result = self._unsubscribe(token)
        if isinstance(result, str):
            return HttpResponse(_render_unsubscribe_page(error=result), status=400, content_type="text/html")
        return HttpResponse(_render_unsubscribe_page(member=result), content_type="text/html")

    # noinspection PyMethodMayBeStatic
    def post(self, request, token):
        result = self._unsubscribe(token)
        if isinstance(result, str):
            return HttpResponse(result, status=400, content_type="text/plain")
        return HttpResponse("Unsubscribed successfully.", status=200, content_type="text/plain")


def _render_unsubscribe_page(member=None, error=None):
    """Return a simple standalone HTML page confirming unsubscribe or showing an error."""
    from django.template.loader import render_to_string

    return render_to_string(
        "mail/email/unsubscribe_done.html",
        {
            "member": member,
            "error": error,
            "frontend_url": (getattr(settings, "FRONTEND_URL", "") or "").strip().rstrip("/"),
        },
    )


def _send_unsubscribe_confirmation(member):
    """Best-effort confirmation email after unsubscribe."""
    from authn.services.email import send_notification_email

    primary_email = member.get_primary_email()
    if not primary_email:
        return

    frontend_url = (getattr(settings, "FRONTEND_URL", "") or "").strip().rstrip("/")
    send_notification_email(
        recipient=primary_email,
        subject="You've been unsubscribed - Innovate to Grow",
        template="mail/email/unsubscribe_confirmation.html",
        context={
            "first_name": member.first_name or "there",
            "account_url": f"{frontend_url}/account" if frontend_url else "",
        },
    )
