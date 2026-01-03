import logging
import os

logger = logging.getLogger(__name__)


def send_email(
    to_address: str,
    subject: str,
    body: str,
    provider: str | None = None,
) -> tuple[bool, str]:
    """
    Send an email via the configured provider.

    Currently supports console logging by default. Hooks are provided for
    Google or other external email APIs; implement actual API calls when
    credentials are available.
    """
    provider_name = provider or os.getenv("EMAIL_PROVIDER", "console")

    if provider_name == "console":
        logger.info("[email][console] to=%s subject=%s body=%s", to_address, subject, body)
        return True, "console"

    # Placeholder for real provider integration
    logger.info("[email][%s] to=%s subject=%s body=%s (stub)", provider_name, to_address, subject, body)
    return True, provider_name


def send_sms(
    to_number: str,
    message: str,
    provider: str | None = None,
) -> tuple[bool, str]:
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
