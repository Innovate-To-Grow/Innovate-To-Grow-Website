"""SNS envelopes for the SES event tests."""

import json

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
