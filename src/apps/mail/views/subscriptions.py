"""One-click unsubscribe and resubscribe endpoints."""

import logging

from django.conf import settings
from django.template.response import TemplateResponse
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.mail.services.tokens.notifications import send_subscription_confirmation
from apps.mail.services.tokens.unsubscribe import (
    build_resubscribe_token,
    get_member_from_oneclick_token,
    get_member_from_resubscribe_token,
)

UNSUBSCRIBE_LINK_INVALID_MESSAGE = "Invalid or expired unsubscribe link."
RESUBSCRIBE_LINK_INVALID_MESSAGE = "Invalid or expired resubscribe link."

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
            _send_unsubscribe_confirmation(member, token)

        return member

    def _handle_unsubscribe(self, request, token):
        result = self._unsubscribe(token)
        if isinstance(result, str):
            return _render_unsubscribe_page(request, error=result, status=400)

        resubscribe_token = build_resubscribe_token(result)
        return _render_unsubscribe_page(
            request,
            member=result,
            resubscribe_token=resubscribe_token,
        )

    # noinspection PyMethodMayBeStatic
    def get(self, request, token):
        return self._handle_unsubscribe(request, token)

    # noinspection PyMethodMayBeStatic
    def post(self, request, token):
        return self._handle_unsubscribe(request, token)


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
            return _render_resubscribe_page(
                request,
                error=RESUBSCRIBE_LINK_INVALID_MESSAGE,
                status=400,
            )

        primary = member.get_primary_contact_email()
        if primary and not primary.subscribe:
            primary.subscribe = True
            primary.save(update_fields=["subscribe"])
            _send_resubscribe_confirmation(member, token)

        return _render_resubscribe_page(request, member=member)


def _render_unsubscribe_page(request, member=None, error=None, resubscribe_token=None, status=200):
    """Return a standalone HTML page confirming unsubscribe or showing an error."""
    backend_url = (getattr(settings, "BACKEND_URL", "") or "").strip().rstrip("/")
    return TemplateResponse(
        request,
        "mail/email/unsubscribe_done.html",
        {
            "member": member,
            "error": error,
            "frontend_url": (getattr(settings, "FRONTEND_URL", "") or "").strip().rstrip("/"),
            "resubscribe_url": f"{backend_url}/mail/resubscribe/{resubscribe_token}/" if resubscribe_token else "",
        },
        status=status,
    )


def _render_resubscribe_page(request, member=None, error=None, status=200):
    """Return a standalone HTML page confirming resubscription or showing an error."""
    return TemplateResponse(
        request,
        "mail/email/resubscribe_done.html",
        {
            "member": member,
            "error": error,
            "frontend_url": (getattr(settings, "FRONTEND_URL", "") or "").strip().rstrip("/"),
        },
        status=status,
    )


def _send_unsubscribe_confirmation(member, event_token):
    """Best-effort confirmation email after unsubscribe."""
    send_subscription_confirmation(
        member=member,
        action="unsubscribe",
        event_token=event_token,
    )


def _send_resubscribe_confirmation(member, event_token):
    """Best-effort confirmation email after resubscribe."""
    send_subscription_confirmation(
        member=member,
        action="resubscribe",
        event_token=event_token,
    )
