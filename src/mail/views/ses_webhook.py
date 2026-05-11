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

from mail.services.ses_events import SesEventError, process_sns_envelope
from mail.services.sns_signature import SnsVerificationError, verify_sns_message

logger = logging.getLogger(__name__)


class SesEventThrottle(AnonRateThrottle):
    """Throttle for SES SNS webhook: 600/minute per source IP."""

    scope = "ses_events"


class SnsEnvelopeParser(BaseParser):
    """Decode SNS POST bodies as JSON regardless of Content-Type."""

    media_type = "*/*"

    def parse(self, stream, media_type=None, parser_context=None):
        raw = stream.read()
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return None


@method_decorator(csrf_exempt, name="dispatch")
class SesEventWebhookView(APIView):
    """AWS SNS to SES event handler."""

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
            logger.warning("SES event processing failed", exc_info=True)
            return Response({"detail": "ok, but logged"}, status=status.HTTP_200_OK)

        return Response({"detail": "ok"}, status=status.HTTP_200_OK)
