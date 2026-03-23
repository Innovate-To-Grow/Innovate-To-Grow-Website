"""
Webhook views for the mail app.
"""

import json
import logging

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from mail.services.sns import handle_subscription_confirmation, process_ses_notification, verify_sns_message

logger = logging.getLogger(__name__)


class SNSWebhookView(APIView):
    """Receive AWS SNS notifications for SES delivery events."""

    permission_classes = [AllowAny]
    authentication_classes = []  # Prevent CSRF from SessionAuthentication

    # noinspection PyMethodMayBeStatic
    def post(self, request):
        # SNS sends Content-Type: text/plain, so parse body directly
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, TypeError):
            return Response({"detail": "Invalid JSON."}, status=status.HTTP_400_BAD_REQUEST)

        message_type = request.headers.get("x-amz-sns-message-type", "")
        if not message_type:
            return Response({"detail": "Missing SNS message type header."}, status=status.HTTP_400_BAD_REQUEST)

        # Verify the message origin
        if not verify_sns_message(body):
            return Response({"detail": "Verification failed."}, status=status.HTTP_403_FORBIDDEN)

        if message_type == "SubscriptionConfirmation":
            handle_subscription_confirmation(body)
        elif message_type == "Notification":
            process_ses_notification(body)
        else:
            logger.debug("Ignoring SNS message type: %s", message_type)

        return Response({"detail": "OK"}, status=status.HTTP_200_OK)
