import logging
import urllib.request
from urllib.parse import parse_qs, urlparse

from core.security import SecurityValidationError, validate_aws_sns_https_url

logger = logging.getLogger(__name__)


def handle_subscription_confirmation(envelope: dict) -> None:
    subscribe_url = envelope.get("SubscribeURL", "")
    try:
        subscribe_url = validate_aws_sns_https_url(subscribe_url)
    except SecurityValidationError:
        logger.warning("Skipping SNS subscription confirmation with invalid URL")
        return

    parsed = urlparse(subscribe_url)
    action = (parse_qs(parsed.query).get("Action") or [""])[0]
    if action != "ConfirmSubscription":
        logger.warning("Skipping SNS subscription confirmation with unexpected action")
        return

    try:
        with urllib.request.urlopen(subscribe_url, timeout=5) as resp:  # noqa: S310
            resp.read()
        logger.info("SNS subscription confirmed")
    except Exception:
        logger.warning("Failed to auto-confirm SNS subscription")
