"""Tests for mail.services.ses_events dispatcher.

Covers the state machine on RecipientLog: a Bounce/Complaint wins over a
late-arriving Delivery, DeliveryDelay is informational only, identical SNS
retries are idempotent, and unknown MessageIds are ignored.
"""

import json
from unittest.mock import patch

from django.test import TestCase

from mail.models import EmailCampaign, RecipientLog
from mail.services.ses_events import SesEventError, process_sns_envelope

SES_MSG_ID = "0100abc-def-0000-0000-ses-message-id"


def _envelope(event_type: str, inner: dict, sns_message_id: str = "sns-1") -> dict:
    """Build an SNS Notification envelope wrapping a given SES event body."""
    body = {"eventType": event_type, "mail": {"messageId": SES_MSG_ID}}
    body.update(inner)
    return {
        "Type": "Notification",
        "MessageId": sns_message_id,
        "TopicArn": "arn:aws:sns:us-west-2:123:ses-events",
        "Message": json.dumps(body),
    }


class ProcessSnsEnvelopeTests(TestCase):
    def setUp(self):
        self.campaign = EmailCampaign.objects.create(subject="Hi", body="B")
        self.log = RecipientLog.objects.create(
            campaign=self.campaign,
            email_address="target@example.com",
            status="sent",
            provider="ses",
            ses_message_id=SES_MSG_ID,
        )

    def _reload(self):
        self.log.refresh_from_db()
        return self.log

    def test_bounce_permanent_sets_status_bounced(self):
        env = _envelope(
            "Bounce",
            {
                "bounce": {
                    "bounceType": "Permanent",
                    "bounceSubType": "General",
                    "timestamp": "2026-04-22T12:00:00.000Z",
                    "bouncedRecipients": [
                        {"emailAddress": "target@example.com", "diagnosticCode": "smtp; 550 no such user"}
                    ],
                }
            },
        )
        process_sns_envelope(env)
        log = self._reload()
        self.assertEqual(log.status, "bounced")
        self.assertEqual(log.bounce_type, "Permanent")
        self.assertEqual(log.bounce_subtype, "General")
        self.assertIn("no such user", log.diagnostic_code)
        self.assertIsNotNone(log.bounced_at)

    def test_bounce_transient_sets_transient_type(self):
        env = _envelope(
            "Bounce",
            {"bounce": {"bounceType": "Transient", "bounceSubType": "MailboxFull", "bouncedRecipients": []}},
        )
        process_sns_envelope(env)
        self.assertEqual(self._reload().bounce_type, "Transient")

    def test_complaint_sets_status_complained(self):
        env = _envelope(
            "Complaint",
            {"complaint": {"complaintFeedbackType": "abuse", "timestamp": "2026-04-22T12:00:00.000Z"}},
        )
        process_sns_envelope(env)
        log = self._reload()
        self.assertEqual(log.status, "complained")
        self.assertEqual(log.complaint_feedback_type, "abuse")

    def test_delivery_sets_status_delivered(self):
        env = _envelope("Delivery", {"delivery": {"timestamp": "2026-04-22T12:00:00.000Z"}})
        process_sns_envelope(env)
        log = self._reload()
        self.assertEqual(log.status, "delivered")
        self.assertIsNotNone(log.delivered_at)

    def test_delivery_does_not_overwrite_prior_bounce(self):
        self.log.status = "bounced"
        self.log.bounce_type = "Permanent"
        self.log.save(update_fields=["status", "bounce_type"])
        env = _envelope("Delivery", {"delivery": {}})
        process_sns_envelope(env)
        self.assertEqual(self._reload().status, "bounced")

    def test_delivery_delay_does_not_change_status(self):
        env = _envelope(
            "DeliveryDelay",
            {"deliveryDelay": {"delayType": "MailboxFull", "expirationTime": "2026-04-23T00:00:00Z"}},
        )
        process_sns_envelope(env)
        log = self._reload()
        self.assertEqual(log.status, "sent")
        self.assertIn("Delayed", log.error_message)
        self.assertEqual(log.last_event_type, "DeliveryDelay")

    def test_reject_sets_status_rejected(self):
        env = _envelope("Reject", {"reject": {"reason": "Bad content"}})
        process_sns_envelope(env)
        log = self._reload()
        self.assertEqual(log.status, "rejected")
        self.assertEqual(log.error_message, "Bad content")

    def test_unknown_message_id_is_silently_ignored(self):
        body = {"eventType": "Bounce", "mail": {"messageId": "not-our-message"}, "bounce": {}}
        env = {"Type": "Notification", "MessageId": "sns-x", "Message": json.dumps(body)}
        process_sns_envelope(env)
        self.assertEqual(self._reload().status, "sent")

    def test_idempotent_same_sns_message_id_is_skipped(self):
        env = _envelope(
            "Bounce",
            {"bounce": {"bounceType": "Permanent", "timestamp": "2026-04-22T12:00:00Z", "bouncedRecipients": []}},
            sns_message_id="sns-42",
        )
        process_sns_envelope(env)
        first_bounced_at = self._reload().bounced_at

        # Replay same SNS MessageId with a different timestamp — should not touch the row.
        env["Message"] = json.dumps(
            {
                "eventType": "Bounce",
                "mail": {"messageId": SES_MSG_ID},
                "bounce": {"bounceType": "Permanent", "timestamp": "2030-01-01T00:00:00Z", "bouncedRecipients": []},
            }
        )
        process_sns_envelope(env)
        self.assertEqual(self._reload().bounced_at, first_bounced_at)

    def test_raises_on_unknown_sns_type(self):
        with self.assertRaises(SesEventError):
            process_sns_envelope({"Type": "SomethingNew"})

    def test_raises_on_notification_with_non_json_message(self):
        with self.assertRaises(SesEventError):
            process_sns_envelope({"Type": "Notification", "MessageId": "x", "Message": "not json"})


class SubscriptionConfirmationTests(TestCase):
    def test_auto_confirm_calls_subscribe_url(self):
        envelope = {
            "Type": "SubscriptionConfirmation",
            "SubscribeURL": "https://sns.us-west-2.amazonaws.com/?Action=ConfirmSubscription&Token=abc",
            "TopicArn": "arn:aws:sns:us-west-2:123:t",
        }
        with patch("mail.services.ses_events.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value.read.return_value = b"<ok/>"
            process_sns_envelope(envelope)
            mock_urlopen.assert_called_once()
            self.assertIn("ConfirmSubscription", mock_urlopen.call_args.args[0])

    def test_non_amazonaws_subscribe_url_is_skipped(self):
        envelope = {
            "Type": "SubscriptionConfirmation",
            "SubscribeURL": "https://evil.example.com/trick",
            "TopicArn": "arn:aws:sns:us-west-2:123:t",
        }
        with patch("mail.services.ses_events.urllib.request.urlopen") as mock_urlopen:
            process_sns_envelope(envelope)
            mock_urlopen.assert_not_called()

    def test_http_subscribe_url_is_skipped(self):
        envelope = {
            "Type": "SubscriptionConfirmation",
            "SubscribeURL": "http://sns.us-west-2.amazonaws.com/?Action=ConfirmSubscription",
            "TopicArn": "arn:aws:sns:us-west-2:123:t",
        }
        with patch("mail.services.ses_events.urllib.request.urlopen") as mock_urlopen:
            process_sns_envelope(envelope)
            mock_urlopen.assert_not_called()
