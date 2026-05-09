import logging
from urllib.parse import parse_qs, urlparse

from core.security import SecurityValidationError, validate_aws_sns_https_url

logger = logging.getLogger(__name__)


def _sns_region_from_topic_arn(topic_arn: str) -> str:
    parts = str(topic_arn or "").split(":")
    if len(parts) < 6 or parts[0] != "arn" or parts[2] != "sns" or not parts[3]:
        raise SecurityValidationError("SNS TopicArn is invalid")
    return parts[3]


def handle_subscription_confirmation(envelope: dict) -> None:
    subscribe_url = envelope.get("SubscribeURL", "")
    try:
        subscribe_url = validate_aws_sns_https_url(subscribe_url)
        topic_arn = str(envelope.get("TopicArn", ""))
        region = _sns_region_from_topic_arn(topic_arn)
    except SecurityValidationError:
        logger.warning("Skipping SNS subscription confirmation with invalid metadata")
        return

    parsed = urlparse(subscribe_url)
    query = parse_qs(parsed.query)
    action = (query.get("Action") or [""])[0]
    if action != "ConfirmSubscription":
        logger.warning("Skipping SNS subscription confirmation with unexpected action")
        return

    token = str(envelope.get("Token") or (query.get("Token") or [""])[0])
    if not token:
        logger.warning("Skipping SNS subscription confirmation without token")
        return

    try:
        import mail.services.ses_events as ses_api

        ses_api.boto3.client("sns", region_name=region).confirm_subscription(
            TopicArn=topic_arn,
            Token=token,
            AuthenticateOnUnsubscribe="true",
        )
        logger.info("SNS subscription confirmed")
    except Exception:
        logger.warning("Failed to auto-confirm SNS subscription")
