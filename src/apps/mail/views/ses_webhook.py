"""SES event webhook views."""

import json
import logging

from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.parsers import BaseParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.core.services.request_limits.view_limits import PolicyRateThrottle
from apps.core.utils.throttle_cache import throttle_cache
from apps.mail.services.ses_events import SesEventError, process_sns_envelope
from apps.mail.services.sns.signature import SnsVerificationError, verify_sns_message

logger = logging.getLogger(__name__)


class SesEventThrottle(PolicyRateThrottle, AnonRateThrottle):
    """Signed SNS deliveries per sending address: 600/minute by default (the "view-ses-events" policy, a fixed
    scope Smart limiting never tightens). Checked only once the SNS signature is verified, so unsigned junk never
    uses up the allowance of the real deliveries."""

    scope = "ses_events"
    policy_scope = "view-ses-events"
    # Keyed on the client address DRF resolves (in production the one the ALB appended), so its history stays out
    # of the file cache. Authenticity comes from the SNS signature check, not from this throttle.
    cache = throttle_cache


class SesRejectedThrottle(PolicyRateThrottle, AnonRateThrottle):
    """Calls whose envelope or signature is rejected, per sending address (the "view-ses-rejected" policy).

    ``allow_request`` only checks (a sender over it is refused before any signature work); ``record`` counts a
    call once it was rejected, so a real SNS sender is never charged for it."""

    scope = "ses_rejected"
    policy_scope = "view-ses-rejected"
    cache = throttle_cache

    def throttle_success(self):
        return True

    def record(self):
        # Nothing to count when the policy is off or there was no key (``allow_request`` stopped early).
        if getattr(self, "history", None) is not None and getattr(self, "key", None) is not None:
            super().throttle_success()


class SnsEnvelopeParser(BaseParser):
    """Decode SNS POST bodies as JSON regardless of Content-Type."""

    media_type = "*/*"

    def parse(self, stream, media_type=None, parser_context=None):
        raw = stream.read()
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            logger.warning("Failed to decode SNS envelope body", exc_info=True)
            return None


@method_decorator(csrf_exempt, name="dispatch")
class SesEventWebhookView(APIView):
    """AWS SNS to SES event handler."""

    permission_classes = [AllowAny]
    authentication_classes = []
    # Throttled inside ``post``: a rejected call and a signed delivery are counted in different buckets.
    throttle_classes = []
    parser_classes = [SnsEnvelopeParser]
    rate_limit_scope = "webhook-ses"

    def _reject(self, rejected, body: dict, code: int) -> Response:
        rejected.record()
        return Response(body, status=code)

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        rejected = SesRejectedThrottle()
        if not rejected.allow_request(request, self):
            self.throttled(request, rejected.wait())
        envelope = request.data
        if not isinstance(envelope, dict):
            return self._reject(rejected, {"detail": "expected JSON object"}, status.HTTP_400_BAD_REQUEST)

        topic_arn = (getattr(settings, "SES_SNS_TOPIC_ARN", "") or "").strip()
        if not topic_arn:
            logger.warning("SES_SNS_TOPIC_ARN not configured; rejecting SNS message")
            return Response({"detail": "webhook not configured"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        try:
            verify_sns_message(envelope, allowed_topic_arns={topic_arn})
        except SnsVerificationError:
            logger.warning("SNS signature rejected", exc_info=True)
            return self._reject(rejected, {"detail": "invalid signature"}, status.HTTP_403_FORBIDDEN)

        signed = SesEventThrottle()
        if not signed.allow_request(request, self):
            self.throttled(request, signed.wait())

        try:
            process_sns_envelope(envelope)
        except SesEventError:
            logger.warning("SES event processing failed", exc_info=True)
            return Response({"detail": "ok, but logged"}, status=status.HTTP_200_OK)

        return Response({"detail": "ok"}, status=status.HTTP_200_OK)
