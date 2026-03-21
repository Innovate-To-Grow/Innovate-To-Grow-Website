"""
AWS SNS notification handler for SES delivery events.

Processes Delivery, Bounce, and Complaint notifications from SES via SNS
and updates the corresponding SESEmailLog records.
"""

import json
import logging
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.utils.dateparse import parse_datetime

from mail.models import SESEmailLog

logger = logging.getLogger(__name__)

# Cache signing certificates for 24 hours
_CERT_CACHE_TTL = 60 * 60 * 24


def _is_valid_sns_cert_url(url: str) -> bool:
    """Validate that the signing certificate URL comes from AWS SNS."""
    parsed = urlparse(url)
    return (
        parsed.scheme == "https"
        and parsed.hostname is not None
        and parsed.hostname.endswith(".amazonaws.com")
        and parsed.hostname.startswith("sns.")
    )


def _validate_topic_arn(topic_arn: str) -> bool:
    """Check the TopicArn against the configured allowlist."""
    allowed = getattr(settings, "SES_SNS_TOPIC_ARN", "").strip()
    if not allowed:
        # No allowlist configured — accept all (development mode)
        return True
    return topic_arn == allowed


def verify_sns_message(message_body: dict) -> bool:
    """Verify an SNS message by checking the TopicArn and certificate URL.

    For production, configure SES_SNS_TOPIC_ARN to restrict to your topic.
    """
    # Verify certificate URL is from AWS
    cert_url = message_body.get("SigningCertURL", "")
    if not _is_valid_sns_cert_url(cert_url):
        logger.warning("SNS message with invalid SigningCertURL: %s", cert_url)
        return False

    # Verify TopicArn if configured
    topic_arn = message_body.get("TopicArn", "")
    if not _validate_topic_arn(topic_arn):
        logger.warning("SNS message with unexpected TopicArn: %s", topic_arn)
        return False

    return True


def handle_subscription_confirmation(message_body: dict):
    """Confirm an SNS subscription by visiting the SubscribeURL."""
    subscribe_url = message_body.get("SubscribeURL", "")
    if not subscribe_url:
        logger.error("SNS SubscriptionConfirmation missing SubscribeURL")
        return

    topic_arn = message_body.get("TopicArn", "")
    logger.info("Confirming SNS subscription for topic: %s", topic_arn)

    try:
        resp = requests.get(subscribe_url, timeout=10)
        resp.raise_for_status()
        logger.info("SNS subscription confirmed successfully for topic: %s", topic_arn)
    except requests.RequestException:
        logger.exception("Failed to confirm SNS subscription for topic: %s", topic_arn)


def process_ses_notification(message_body: dict):
    """Process an SES event notification and update the matching SESEmailLog."""
    # The SES notification is nested inside the SNS Message field as a JSON string
    raw_message = message_body.get("Message", "")
    try:
        ses_event = json.loads(raw_message)
    except (json.JSONDecodeError, TypeError):
        logger.error("Failed to parse SES notification Message as JSON")
        return

    notification_type = ses_event.get("notificationType", "")
    mail_obj = ses_event.get("mail", {})
    message_id = mail_obj.get("messageId", "")

    if not message_id:
        logger.warning("SES notification missing mail.messageId")
        return

    if notification_type == "Delivery":
        delivery = ses_event.get("delivery", {})
        timestamp = parse_datetime(delivery.get("timestamp", ""))
        updated = SESEmailLog.objects.filter(ses_message_id=message_id).update(
            delivery_status=SESEmailLog.DeliveryStatus.DELIVERED,
            delivery_timestamp=timestamp,
        )
        logger.info("SES Delivery: message_id=%s, updated=%d records", message_id, updated)

    elif notification_type == "Bounce":
        bounce = ses_event.get("bounce", {})
        timestamp = parse_datetime(bounce.get("timestamp", ""))
        updated = SESEmailLog.objects.filter(ses_message_id=message_id).update(
            delivery_status=SESEmailLog.DeliveryStatus.BOUNCED,
            delivery_timestamp=timestamp,
            bounce_type=bounce.get("bounceType", ""),
            bounce_subtype=bounce.get("bounceSubType", ""),
        )
        logger.info("SES Bounce: message_id=%s, type=%s, updated=%d", message_id, bounce.get("bounceType"), updated)

    elif notification_type == "Complaint":
        complaint = ses_event.get("complaint", {})
        timestamp = parse_datetime(complaint.get("timestamp", ""))
        updated = SESEmailLog.objects.filter(ses_message_id=message_id).update(
            delivery_status=SESEmailLog.DeliveryStatus.COMPLAINED,
            delivery_timestamp=timestamp,
            complaint_feedback_type=complaint.get("complaintFeedbackType", ""),
        )
        logger.info("SES Complaint: message_id=%s, updated=%d", message_id, updated)

    else:
        logger.debug("Ignoring SES notification type: %s", notification_type)
