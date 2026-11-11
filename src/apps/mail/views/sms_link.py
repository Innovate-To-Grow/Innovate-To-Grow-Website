"""SMS short links and the short ``/register`` link.

``POST /mail/sms-link/`` exchanges the token of an ``/l/<token>`` link the SPA opened (``{"token": "..."}``). A
personal link signs its member in once (the same payload as the emailed login link, plus ``kind: "sign_in"``); any
other link, and a personal one while personal sign-in links are off, answers ``kind: "redirect"``. Both carry ``redirect_to``, an internal path. A rejection is a 400 with the
login link's codes (``token_required``, ``invalid_link``, ``expired``, ``already_used``); it never says whose link it
was. It is limited by the request limiter's P0 ``auth-email-link`` scope like the emailed login link: the 128-bit token
is the control, and campus users share one public IP.

``GET /mail/register-link/`` answers where ``/register`` leads (``{"path": "/login"}`` unless staff chose a page).
"""

import logging

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authn.views.helpers import build_auth_success_payload, read_body_string
from apps.mail.services.sms.links import open_link
from apps.mail.services.sms.register_link import register_destination

from .login_link import CODE_MISSING_CREDENTIAL

logger = logging.getLogger(__name__)

_DETAILS = {
    "invalid_link": "Invalid link.",
    "expired": "This link has expired.",
    "already_used": "This link has already been used.",
}


def _answer(body: dict, http_status: int) -> Response:
    # A sign-in answer carries tokens: no answer of this endpoint may be stored by a browser or a proxy.
    response = Response(body, status=http_status)
    response["Cache-Control"] = "no-store"
    return response


def _reject(code: str, *, reason: str = "", redirect_to: str = "") -> Response:
    # The token is never logged.
    logger.info("SMS link rejected: reason=%s", reason or code)
    body = {"detail": _DETAILS.get(code, "Token is required."), "code": code}
    if redirect_to:
        body["redirect_to"] = redirect_to
    return _answer(body, status.HTTP_400_BAD_REQUEST)


class SmsLinkView(APIView):
    """Exchange an SMS short-link token for a session (a personal link) or a destination (any other)."""

    rate_limit_scope = "auth-email-link"
    permission_classes = [AllowAny]
    # Authenticated by the token in the body: a stale, expired or other-account Bearer must never 401 this.
    authentication_classes = []
    # No per-IP throttle (campus users share one IP): the request limiter's scope and the 128-bit token are the
    # controls, and a personal link works once.
    throttle_classes = []

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        token = read_body_string(request, "token")
        if not token:
            return _reject(CODE_MISSING_CREDENTIAL)
        opened = open_link(token)
        if opened.kind == "rejected":
            return _reject(opened.code, reason=opened.reason, redirect_to=opened.redirect_to)
        if opened.kind == "redirect":
            return _answer({"kind": "redirect", "redirect_to": opened.redirect_to}, status.HTTP_200_OK)
        payload = build_auth_success_payload(opened.member, "Login successful.")
        payload.update(kind="sign_in", redirect_to=opened.redirect_to)
        return _answer(payload, status.HTTP_200_OK)


class RegisterLinkView(APIView):
    """Where the short ``/register`` link leads (Mail → SMS Settings); public and cached."""

    rate_limit_scope = "public-read"
    permission_classes = [AllowAny]
    authentication_classes = []

    # noinspection PyMethodMayBeStatic
    def get(self, request):
        return Response({"path": register_destination()}, status=status.HTTP_200_OK)
