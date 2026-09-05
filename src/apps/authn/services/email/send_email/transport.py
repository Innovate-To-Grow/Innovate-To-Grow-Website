import logging

from apps.core.services.aws.provider_outcomes import NO_PROVIDER_RETRIES
from apps.core.services.email import EmailDeliveryError, EmailMessage, deliver_email

logger = logging.getLogger(__name__)


def _load_config():
    from apps.core.models import EmailServiceConfig

    return EmailServiceConfig.load()


def _send_via_ses(
    *,
    config,
    recipient: str,
    subject: str,
    html_body: str,
    before_provider_call=None,
    raise_provider_errors: bool = False,
) -> bool:
    if not config.delivery_configured:
        return False
    try:
        deliver_email(
            EmailMessage(subject=subject, to=(recipient,), html_body=html_body),
            config=config,
            before_provider_call=before_provider_call,
            retry_config=NO_PROVIDER_RETRIES,
        )
        return True
    except EmailDeliveryError:
        logger.exception("Email delivery failed")
        if raise_provider_errors:
            # Neutral SES/SMTP errors already preserve ProviderDeliveryError's
            # outcome contract; retain the concrete classification and cause.
            raise
        return False
