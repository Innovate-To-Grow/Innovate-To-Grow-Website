"""One-click unsubscribe and resubscribe endpoints.

Both are standalone HTML pages authenticated only by the signed token in the URL. They never read the request
body: an RFC 8058 one-click POST from a mailbox provider may use any content type, and the token is the whole
request.
"""

import logging

from django.conf import settings
from django.template.response import TemplateResponse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.mail.services.subscriptions import (
    member_has_subscribed_email,
    resubscribe_emails,
    unsubscribe_all_emails,
)
from apps.mail.services.tokens.unsubscribe import (
    build_resubscribe_token,
    get_member_from_oneclick_token,
    load_resubscribe_token,
)

UNSUBSCRIBE_LINK_INVALID_MESSAGE = "Invalid or expired unsubscribe link."
RESUBSCRIBE_LINK_INVALID_MESSAGE = "Invalid or expired resubscribe link."

logger = logging.getLogger(__name__)


# The pages carry live tokens (the done page a resubscribe token), so no cache may keep them.
@method_decorator(never_cache, name="dispatch")
class _SubscriptionLinkView(APIView):
    """Shared request policy for the token-in-URL subscription pages."""

    permission_classes = [AllowAny]
    # No per-IP throttle by design: campus users share one public IP, and the signed token is the control.
    throttle_classes = []

    def perform_content_negotiation(self, request, force=False):
        # The HTML page is the only representation. DRF would otherwise answer 406 to an unusual Accept header
        # (or 404 to ``?format=``) before the handler runs, and the mailbox provider's unsubscribe would be lost.
        return super().perform_content_negotiation(request, force=True)


class OneClickUnsubscribeView(_SubscriptionLinkView):
    """Unsubscribe endpoint used by email clients (RFC 8058 POST) and the footer link (GET, then a form POST)."""

    # Authenticated by the signed token in the URL: a stale, expired or other-account Bearer must never 401 this.
    authentication_classes = []
    # HEAD runs ``get``, which has no side effects.
    http_method_names = ["get", "head", "post"]

    # noinspection PyMethodMayBeStatic
    def get(self, request, token):
        # Link scanners and prefetchers GET every link in a message, so GET only asks for confirmation.
        member = _member_from_unsubscribe_token(token)
        if member is None:
            return _render_unsubscribe_error(request)
        if member_has_subscribed_email(member):
            return _render_page(request, "mail/email/unsubscribe_confirm.html", {"member": member})
        # Already unsubscribed (e.g. the one-click header ran first): no resubscribe offer on a page a scanner
        # can fetch. The account page manages each address.
        return _render_unsubscribe_done(request, member)

    # noinspection PyMethodMayBeStatic
    def post(self, request, token):
        member = _member_from_unsubscribe_token(token)
        if member is None:
            return _render_unsubscribe_error(request)
        changed_ids = unsubscribe_all_emails(member)
        return _render_unsubscribe_done(request, member, resubscribe_token=_resubscribe_token_for(member, changed_ids))


class ResubscribeView(_SubscriptionLinkView):
    """Re-subscribe the addresses a one-click unsubscribe just turned off."""

    # Authenticated by the signed token in the URL: a stale, expired or other-account Bearer must never 401 this.
    authentication_classes = []
    http_method_names = ["post"]

    # noinspection PyMethodMayBeStatic
    def post(self, request, token):
        try:
            member, email_ids = load_resubscribe_token(token)
        except ValueError:
            logger.info("Resubscribe token rejected")
            return _render_page(
                request,
                "mail/email/resubscribe_done.html",
                {"error": RESUBSCRIBE_LINK_INVALID_MESSAGE},
                status=400,
            )

        changed_ids = resubscribe_emails(member, email_ids)
        return _render_page(
            request,
            "mail/email/resubscribe_done.html",
            {"member": member, "changed": bool(changed_ids)},
        )


def _member_from_unsubscribe_token(token):
    try:
        return get_member_from_oneclick_token(token)
    except ValueError:
        logger.info("One-click unsubscribe token rejected")
        return None


def _resubscribe_token_for(member, changed_ids):
    """Token for the done page's resubscribe button, or ``None`` for no button.

    Only a POST that actually turned addresses off offers an undo, and only of those addresses. A replay, or a POST
    for a member who opted out elsewhere (e.g. on the account page), gets no button: a forwarded or leaked link
    must not be a way to turn a deliberate opt-out back on. Inactive members get no button either: the resubscribe
    link rejects them.
    """
    if not changed_ids or not member.is_active:
        return None
    return build_resubscribe_token(member, email_ids=changed_ids)


def _render_unsubscribe_error(request):
    return _render_page(
        request,
        "mail/email/unsubscribe_done.html",
        {"error": UNSUBSCRIBE_LINK_INVALID_MESSAGE},
        status=400,
    )


def _render_unsubscribe_done(request, member, resubscribe_token=None):
    # Relative to this page (``.../unsubscribe/<token>/``), so the form stays same-origin for CSP
    # ``form-action 'self'`` whether the page was reached on the backend host or through the /api proxy.
    resubscribe_url = f"../../resubscribe/{resubscribe_token}/" if resubscribe_token else ""
    return _render_page(
        request,
        "mail/email/unsubscribe_done.html",
        {"member": member, "resubscribe_url": resubscribe_url},
    )


def _render_page(request, template, context, status=200):
    """Render a standalone subscription page; every page links to the account's email preferences."""
    return TemplateResponse(
        request,
        template,
        {
            "frontend_url": (getattr(settings, "FRONTEND_URL", "") or "").strip().rstrip("/"),
            **context,
        },
        status=status,
    )
