"""One-click unsubscribe and resubscribe endpoints."""

import logging

from django.conf import settings
from django.http import HttpResponse
from django.template.loader import render_to_string
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from authn.services import email as email_api
from mail.services.unsubscribe_token import (
    build_resubscribe_token,
    get_member_from_oneclick_token,
    get_member_from_resubscribe_token,
)

from .constants import RESUBSCRIBE_LINK_INVALID_MESSAGE, UNSUBSCRIBE_LINK_INVALID_MESSAGE

logger = logging.getLogger(__name__)


class OneClickUnsubscribeView(APIView):
    """Unsubscribe endpoint used by email clients and direct links."""

    permission_classes = [AllowAny]
    http_method_names = ["get", "post"]

    def _unsubscribe(self, token):
        try:
            member = get_member_from_oneclick_token(token)
        except ValueError:
            logger.info("One-click unsubscribe token rejected")
            return UNSUBSCRIBE_LINK_INVALID_MESSAGE

        primary = member.get_primary_contact_email()
        if primary and primary.subscribe:
            primary.subscribe = False
            primary.save(update_fields=["subscribe"])
            _send_unsubscribe_confirmation(member)

        return member

    def _handle_unsubscribe(self, token):
        result = self._unsubscribe(token)
        if isinstance(result, str):
            return HttpResponse(_render_unsubscribe_page(error=result), status=400, content_type="text/html")

        resubscribe_token = build_resubscribe_token(result)
        return HttpResponse(
            _render_unsubscribe_page(member=result, resubscribe_token=resubscribe_token),
            content_type="text/html",
        )

    # noinspection PyMethodMayBeStatic
    def get(self, request, token):
        return self._handle_unsubscribe(token)

    # noinspection PyMethodMayBeStatic
    def post(self, request, token):
        return self._handle_unsubscribe(token)


class ResubscribeView(APIView):
    """Re-subscribe a member who just unsubscribed."""

    permission_classes = [AllowAny]
    http_method_names = ["post"]

    # noinspection PyMethodMayBeStatic
    def post(self, request, token):
        try:
            member = get_member_from_resubscribe_token(token)
        except ValueError:
            logger.info("Resubscribe token rejected")
            return HttpResponse(
                _render_resubscribe_page(error=RESUBSCRIBE_LINK_INVALID_MESSAGE),
                status=400,
                content_type="text/html",
            )

        primary = member.get_primary_contact_email()
        if primary and not primary.subscribe:
            primary.subscribe = True
            primary.save(update_fields=["subscribe"])
            _send_resubscribe_confirmation(member)

        return HttpResponse(_render_resubscribe_page(member=member), content_type="text/html")


def _render_unsubscribe_page(member=None, error=None, resubscribe_token=None):
    """Return a standalone HTML page confirming unsubscribe or showing an error."""
    backend_url = (getattr(settings, "BACKEND_URL", "") or "").strip().rstrip("/")
    return render_to_string(
        "mail/email/unsubscribe_done.html",
        {
            "member": member,
            "error": error,
            "frontend_url": (getattr(settings, "FRONTEND_URL", "") or "").strip().rstrip("/"),
            "resubscribe_url": f"{backend_url}/mail/resubscribe/{resubscribe_token}/" if resubscribe_token else "",
        },
    )


def _render_resubscribe_page(member=None, error=None):
    """Return a standalone HTML page confirming resubscription or showing an error."""
    return render_to_string(
        "mail/email/resubscribe_done.html",
        {
            "member": member,
            "error": error,
            "frontend_url": (getattr(settings, "FRONTEND_URL", "") or "").strip().rstrip("/"),
        },
    )


def _send_unsubscribe_confirmation(member):
    """Best-effort confirmation email after unsubscribe."""
    primary_email = member.get_primary_email()
    if not primary_email:
        return

    frontend_url = (getattr(settings, "FRONTEND_URL", "") or "").strip().rstrip("/")
    email_api.send_notification_email(
        recipient=primary_email,
        subject="You've been unsubscribed - Innovate to Grow",
        template="mail/email/unsubscribe_confirmation.html",
        context={
            "first_name": member.first_name or "there",
            "account_url": f"{frontend_url}/account" if frontend_url else "",
        },
    )


def _send_resubscribe_confirmation(member):
    """Best-effort confirmation email after resubscribe."""
    primary_email = member.get_primary_email()
    if not primary_email:
        return

    frontend_url = (getattr(settings, "FRONTEND_URL", "") or "").strip().rstrip("/")
    email_api.send_notification_email(
        recipient=primary_email,
        subject="You've been resubscribed - Innovate to Grow",
        template="mail/email/resubscribe_confirmation.html",
        context={
            "first_name": member.first_name or "there",
            "account_url": f"{frontend_url}/account" if frontend_url else "",
        },
    )
