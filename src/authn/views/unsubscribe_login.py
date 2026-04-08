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


def _send_unsubscribe_confirmation(member):
    """Best-effort confirmation email after unsubscribe."""
    from django.conf import settings

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


class UnsubscribeAutoLoginView(APIView):
    """Exchange a signed unsubscribe-email token for JWT credentials."""

    permission_classes = [AllowAny]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        token = request.data.get("token", "").strip()
        if not token:
            return Response({"detail": "Token is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            member = get_member_from_unsubscribe_token(token)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        primary = member.get_primary_contact_email()
        if primary and primary.subscribe:
            primary.subscribe = False
            primary.save(update_fields=["subscribe"])
            _send_unsubscribe_confirmation(member)

        payload = build_auth_success_payload(member, "You have been unsubscribed.")
        payload["unsubscribed"] = True
        return Response(payload, status=status.HTTP_200_OK)
