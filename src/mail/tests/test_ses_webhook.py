"""Tests for the SesEventWebhookView at /mail/ses/events/.

Signature verification is exhaustively exercised in test_sns_signature.py;
here we mock verify_sns_message and assert the view wires request flow,
CSRF-exemption, and response codes correctly.
"""

import json
from unittest.mock import patch

from django.test import TestCase, override_settings

from mail.models import EmailCampaign, RecipientLog
from mail.services.ses_events import SesEventError
from mail.services.sns_signature import SnsVerificationError

SES_MSG_ID = "ses-msg-webhook-test"


def _bounce_envelope() -> dict:
    body = {
        "eventType": "Bounce",
        "mail": {"messageId": SES_MSG_ID},
        "bounce": {
            "bounceType": "Permanent",
            "bounceSubType": "General",
            "timestamp": "2026-04-22T12:00:00.000Z",
            "bouncedRecipients": [{"emailAddress": "target@example.com", "diagnosticCode": "smtp; 550"}],
        },
    }
    return {
        "Type": "Notification",
        "MessageId": "sns-1",
        "TopicArn": "arn:aws:sns:us-west-2:123:ses-events",
        "Message": json.dumps(body),
    }


class SesEventWebhookViewTests(TestCase):
    def setUp(self):
        self.campaign = EmailCampaign.objects.create(subject="Hi", body="B")
        self.log = RecipientLog.objects.create(
            campaign=self.campaign,
            email_address="target@example.com",
            status="sent",
            provider="ses",
            ses_message_id=SES_MSG_ID,
        )

    @patch("mail.views.verify_sns_message")
    def test_valid_bounce_updates_log_and_returns_200(self, mock_verify):
        response = self.client.post(
            "/mail/ses/events/",
            data=json.dumps(_bounce_envelope()),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        mock_verify.assert_called_once()
        self.log.refresh_from_db()
        self.assertEqual(self.log.status, "bounced")

    @patch("mail.views.verify_sns_message", side_effect=SnsVerificationError("bad sig"))
    def test_bad_signature_returns_403(self, mock_verify):
        with patch("mail.views.logger.warning") as warning:
            response = self.client.post(
                "/mail/ses/events/",
                data=json.dumps(_bounce_envelope()),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 403)
        warning.assert_called_once_with("SNS signature rejected", exc_info=True)
        self.log.refresh_from_db()
        self.assertEqual(self.log.status, "sent")

    @patch("mail.views.process_sns_envelope", side_effect=SesEventError("bad event"))
    @patch("mail.views.verify_sns_message")
    def test_processing_error_logs_stack_trace_and_returns_200(self, _mock_verify, _mock_process):
        with patch("mail.views.logger.warning") as warning:
            response = self.client.post(
                "/mail/ses/events/",
                data=json.dumps(_bounce_envelope()),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        warning.assert_called_once_with("SES event processing failed", exc_info=True)

    @patch("mail.views.verify_sns_message")
    def test_non_dict_body_returns_400(self, mock_verify):
        response = self.client.post(
            "/mail/ses/events/",
            data=json.dumps(["not", "an", "object"]),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    @patch("mail.views.verify_sns_message")
    def test_text_plain_content_type_is_accepted(self, mock_verify):
        """SNS sometimes posts SubscriptionConfirmation as text/plain."""
        envelope = {
            "Type": "SubscriptionConfirmation",
            "SubscribeURL": "https://evil.example.com/",  # host mismatch → skipped inside dispatcher
            "TopicArn": "arn:aws:sns:us-west-2:123:t",
        }
        response = self.client.post(
            "/mail/ses/events/",
            data=json.dumps(envelope),
            content_type="text/plain",
        )
        self.assertEqual(response.status_code, 200)

    @patch("mail.views.verify_sns_message")
    def test_csrf_token_is_not_required(self, mock_verify):
        """AWS never sends a CSRF token; the endpoint must accept POSTs without one."""
        response = self.client.post(
            "/mail/ses/events/",
            data=json.dumps(_bounce_envelope()),
            content_type="application/json",
            enforce_csrf_checks=True,
        )
        self.assertNotEqual(response.status_code, 403)

    @override_settings(SES_SNS_TOPIC_ARN="arn:aws:sns:us-west-2:123:ses-events")
    @patch("mail.views.verify_sns_message")
    def test_topic_arn_allowlist_passed_through_when_configured(self, mock_verify):
        self.client.post(
            "/mail/ses/events/",
            data=json.dumps(_bounce_envelope()),
            content_type="application/json",
        )
        kwargs = mock_verify.call_args.kwargs
        self.assertEqual(kwargs["allowed_topic_arns"], {"arn:aws:sns:us-west-2:123:ses-events"})
