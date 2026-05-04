import json
import logging

from django.conf import settings
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.parsers import BaseParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from authn.throttles import LoginRateThrottle
from authn.views.helpers import build_auth_success_payload

from .login_redirects import get_magic_login_redirect_path
from .models import MagicLoginToken
from .services.ses_events import SesEventError, process_sns_envelope
from .services.sns_signature import SnsVerificationError, verify_sns_message
from .services.unsubscribe_token import (
    build_resubscribe_token,
    get_member_from_oneclick_token,
    get_member_from_resubscribe_token,
)

logger = logging.getLogger(__name__)

UNSUBSCRIBE_LINK_INVALID_MESSAGE = "Invalid or expired unsubscribe link."
RESUBSCRIBE_LINK_INVALID_MESSAGE = "Invalid or expired resubscribe link."


class MagicLoginView(APIView):
    """Exchange a campaign login token for JWT credentials."""

    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        token = request.data.get("token", "").strip()
        if not token:
            return Response({"detail": "Token is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            magic = MagicLoginToken.objects.select_related("member", "campaign").get(token=token)
        except MagicLoginToken.DoesNotExist:
            return Response({"detail": "Invalid login link."}, status=status.HTTP_400_BAD_REQUEST)

        if magic.is_expired:
            return Response({"detail": "This login link has expired."}, status=status.HTTP_400_BAD_REQUEST)
        magic.record_use()
        payload = build_auth_success_payload(magic.member, "Login successful.")
        payload["redirect_to"] = get_magic_login_redirect_path(magic.campaign)
        return Response(payload, status=status.HTTP_200_OK)


class OneClickUnsubscribeView(APIView):
    """Unsubscribe endpoint.

    - **POST** (RFC 8058): email clients call this automatically.
    - **GET**: directly unsubscribes the member.
    """

    permission_classes = [AllowAny]
    http_method_names = ["get", "post"]

    def _unsubscribe(self, token):
        """Validate *token*, opt the member out, and return the member or an error string."""
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
            _render_unsubscribe_page(member=result, resubscribe_token=resubscribe_token), content_type="text/html"
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


class SesEventThrottle(AnonRateThrottle):
    """Throttle for SES SNS webhook: 600/minute per source IP."""

    scope = "ses_events"


class SnsEnvelopeParser(BaseParser):
    """Decode SNS POST bodies as JSON regardless of Content-Type.

    SNS posts application/json for notifications but sometimes text/plain
    for SubscriptionConfirmation; accept both.
    """

    media_type = "*/*"

    def parse(self, stream, media_type=None, parser_context=None):
        raw = stream.read()
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return None


@method_decorator(csrf_exempt, name="dispatch")
class SesEventWebhookView(APIView):
    """AWS SNS → SES event handler.

    Public endpoint; genuine-origin trust is anchored in SNS signature
    verification (see ``services.sns_signature``) plus a ``TopicArn``
    allowlist when ``SES_SNS_TOPIC_ARN`` is configured.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [SesEventThrottle]
    parser_classes = [SnsEnvelopeParser]

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        envelope = request.data
        if not isinstance(envelope, dict):
            return Response({"detail": "expected JSON object"}, status=status.HTTP_400_BAD_REQUEST)

        topic_arn = (getattr(settings, "SES_SNS_TOPIC_ARN", "") or "").strip()
        allowed = {topic_arn} if topic_arn else None

        try:
            verify_sns_message(envelope, allowed_topic_arns=allowed)
        except SnsVerificationError:
            logger.warning("SNS signature rejected", exc_info=True)
            return Response({"detail": "invalid signature"}, status=status.HTTP_403_FORBIDDEN)

        try:
            process_sns_envelope(envelope)
        except SesEventError:
            # Return 200 anyway — AWS retries repeatedly on 5xx and will
            # saturate this endpoint on a permanent decoding bug. The
            # failure is logged; operators can replay from the SNS DLQ.
            logger.warning("SES event processing failed", exc_info=True)
            return Response({"detail": "ok, but logged"}, status=status.HTTP_200_OK)

        return Response({"detail": "ok"}, status=status.HTTP_200_OK)


def _render_unsubscribe_page(member=None, error=None, resubscribe_token=None):
    """Return a simple standalone HTML page confirming unsubscribe or showing an error."""
    from django.template.loader import render_to_string

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
    """Return a simple standalone HTML page confirming resubscription or showing an error."""
    from django.template.loader import render_to_string

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


def _send_resubscribe_confirmation(member):
    """Best-effort confirmation email after resubscribe."""
    from authn.services.email import send_notification_email

    primary_email = member.get_primary_email()
    if not primary_email:
        return

    frontend_url = (getattr(settings, "FRONTEND_URL", "") or "").strip().rstrip("/")
    send_notification_email(
        recipient=primary_email,
        subject="You've been resubscribed - Innovate to Grow",
        template="mail/email/resubscribe_confirmation.html",
        context={
            "first_name": member.first_name or "there",
            "account_url": f"{frontend_url}/account" if frontend_url else "",
        },
    )
