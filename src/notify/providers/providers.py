import logging
import os
from typing import Tuple
from django.conf import settings
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


def send_email(
    to_address: str,
    subject: str,
    body: str,
    provider: str | None = None,
) -> Tuple[bool, str]:
    """
    Send an email via the configured provider.

    Currently supports console logging and Amazon SES. Hooks are provided for
    other external email APIs; implement actual API calls when credentials are available.
    """
    provider_name = provider or os.getenv("EMAIL_PROVIDER", "console")

    if provider_name == "console":
        logger.info("[email][console] to=%s subject=%s body=%s", to_address, subject, body)
        return True, "console"

    if provider_name == "ses":
        return _send_email_ses(to_address, subject, body)

    # Placeholder for other provider integrations
    logger.info("[email][%s] to=%s subject=%s body=%s (stub)", provider_name, to_address, subject, body)
    return True, provider_name


def _send_email_ses(
    to_address: str,
    subject: str,
    body: str,
) -> Tuple[bool, str]:
    """
    Send an email via Amazon SES.

    Args:
        to_address: Recipient email address
        subject: Email subject
        body: Email body (plain text)

    Returns:
        Tuple of (success: bool, provider_name: str)
    """
    try:
        import boto3
    except ImportError:
        logger.error("[email][ses] boto3 not installed. Install with: pip install boto3")
        return False, "ses"

    # Check required settings
    if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
        logger.error("[email][ses] AWS credentials not configured. Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in .env")
        return False, "ses"

    if not settings.AWS_SES_FROM_EMAIL:
        logger.error("[email][ses] AWS_SES_FROM_EMAIL not configured. Set in .env")
        return False, "ses"

    try:
        # Create SES client
        ses_client = boto3.client(
            'ses',
            region_name=settings.AWS_SES_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

        # Send email
        response = ses_client.send_email(
            Source=settings.AWS_SES_FROM_EMAIL,
            Destination={
                'ToAddresses': [to_address]
            },
            Message={
                'Subject': {
                    'Data': subject,
                    'Charset': 'UTF-8'
                },
                'Body': {
                    'Text': {
                        'Data': body,
                        'Charset': 'UTF-8'
                    }
                }
            }
        )

        message_id = response.get('MessageId', 'unknown')
        logger.info("[email][ses] sent successfully to=%s message_id=%s", to_address, message_id)
        return True, "ses"

    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_message = e.response.get('Error', {}).get('Message', str(e))
        logger.error("[email][ses] AWS error sending to=%s code=%s message=%s", to_address, error_code, error_message)
        return False, "ses"

    except Exception as e:
        logger.error("[email][ses] Unexpected error sending to=%s error=%s", to_address, str(e), exc_info=True)
        return False, "ses"


def send_sms(
    to_number: str,
    message: str,
    provider: str | None = None,
) -> Tuple[bool, str]:
    """
    Send an SMS via the configured provider.

    Defaults to console logging. Add real implementation for Google/other SMS
    providers when credentials are available.
    """
    provider_name = provider or os.getenv("SMS_PROVIDER", "console")

    if provider_name == "console":
        logger.info("[sms][console] to=%s message=%s", to_number, message)
        return True, "console"

    # Placeholder for real provider integration
    logger.info("[sms][%s] to=%s message=%s (stub)", provider_name, to_number, message)
    return True, provider_name

