"""Login-link endpoint for emailed one-click login (campaign and ticket emails).

Served at ``/mail/login-link/`` and the legacy alias ``/mail/magic-login/``
(tokens issued before the rename remain valid).
"""

import logging

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authn.views.helpers import build_auth_success_payload, read_body_string
from apps.mail.models import LoginLinkToken

logger = logging.getLogger(__name__)

# Stable machine-readable ``code`` returned next to ``detail`` on every rejection. The first constant is not named
# after its "token_required" value: a ``*_TOKEN_*`` name makes Bandit (B105) read the code string as a hardcoded secret.
CODE_MISSING_CREDENTIAL = "token_required"
CODE_INVALID_LINK = "invalid_link"
CODE_EXPIRED = "expired"
CODE_ALREADY_USED = "already_used"


def _reject(request, detail, code, *, reason=None, member_id=None, redirect_to=None):
    """Log a rejected exchange and build its 400 response.

    ``reason`` is the internal cause for the log; it defaults to ``code`` and only differs where the
    response must not reveal it (an inactive member looks like an unknown token). The token is never logged.
    ``redirect_to`` is added to the body only when given; see :func:`_reject_spent`.
    """
    logger.info(
        "Login link rejected: reason=%s member_id=%s authorization_header=%s",
        reason or code,
        member_id,
        bool(request.headers.get("Authorization")),
    )
    body = {"detail": detail, "code": code}
    if redirect_to is not None:
        body["redirect_to"] = redirect_to
    return Response(body, status=status.HTTP_400_BAD_REQUEST)


def _reject_spent(request, link, detail, code):
    """Reject a genuine link that can no longer be used (``expired`` / ``already_used``).

    The body also carries the link's own post-login destination, so a client that falls back to another
    sign-in method can still land where the email intended. This is not an account-state leak: it is the
    campaign or ticket landing path (already validated as internal by ``effective_redirect_path``), the same
    value a successful exchange returns, and only a caller holding the real, unguessable token gets here.
    Unknown tokens and inactive members are rejected earlier, through :func:`_reject` without it.
    """
    return _reject(request, detail, code, member_id=link.member_id, redirect_to=link.effective_redirect_path)


class LoginLinkView(APIView):
    """Exchange an emailed login-link token for JWT credentials."""

    permission_classes = [AllowAny]
    # Authenticated by the one-time token in the body: a stale, expired or other-account Bearer must never 401 this.
    authentication_classes = []
    # No per-IP throttle by design: campus users share one public IP, and the ~384-bit single-use token is the control.
    throttle_classes = []

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        token = read_body_string(request, "token")
        if not token:
            return _reject(request, "Token is required.", CODE_MISSING_CREDENTIAL)

        try:
            link = LoginLinkToken.objects.select_related("member", "campaign", "registration__event").get(token=token)
        except LoginLinkToken.DoesNotExist:
            return _reject(request, "Invalid login link.", CODE_INVALID_LINK, reason="unknown_token")

        # Same generic message and code as an unknown token — don't reveal account state.
        if not link.member.is_active:
            return _reject(
                request, "Invalid login link.", CODE_INVALID_LINK, reason="inactive_member", member_id=link.member_id
            )

        if link.is_expired:
            return _reject_spent(request, link, "This login link has expired.", CODE_EXPIRED)

        if link.is_reusable:
            # Conditional on expiry so a concurrent revoke/expiry can't slip through.
            if not link.record_reusable_use():
                return _reject_spent(request, link, "This login link has expired.", CODE_EXPIRED)
        elif not link.try_mark_used():
            return _reject_spent(request, link, "This login link has already been used.", CODE_ALREADY_USED)

        payload = build_auth_success_payload(link.member, "Login successful.")
        payload["redirect_to"] = link.effective_redirect_path
        return Response(payload, status=status.HTTP_200_OK)
