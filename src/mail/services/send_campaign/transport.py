import logging
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from django.conf import settings

from core.models import EmailServiceConfig

logger = logging.getLogger(__name__)


@dataclass
class SesSendResult:
    """Outcome of a single SES send_raw_email call."""

    message_id: str = ""
    error: str = ""


def _get_ses_client(config):
    if not config.ses_configured:
        return None
    try:
        import boto3

        return boto3.client(
            "ses",
            region_name=config.ses_region,
            aws_access_key_id=config.ses_access_key_id,
            aws_secret_access_key=config.ses_secret_access_key,
        )
    except Exception:
        logger.exception("Failed to create SES client")
        return None


def _get_configuration_set_name(config: EmailServiceConfig) -> str:
    name = getattr(config, "ses_configuration_set_name", "") or ""
    if not name:
        name = getattr(settings, "SES_CONFIGURATION_SET_NAME", "") or ""
    return name.strip()


def _build_unsubscribe_headers(unsubscribe_url):
    if not unsubscribe_url:
        return {}
    return {
        "List-Unsubscribe": f"<{unsubscribe_url}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }


def _build_raw_ses_message(*, source, recipient, subject, html_body, extra_headers):
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = source
    message["To"] = recipient
    for key, value in extra_headers.items():
        message[key] = value
    message.attach(MIMEText(html_body, "html", "utf-8"))
    return message.as_string()


def _send_via_ses(
    *,
    ses_client,
    source,
    recipient,
    subject,
    html_body,
    unsubscribe_url="",
    configuration_set="",
) -> SesSendResult:
    try:
        kwargs = {
            "Source": source,
            "Destinations": [recipient],
            "RawMessage": {
                "Data": _build_raw_ses_message(
                    source=source,
                    recipient=recipient,
                    subject=subject,
                    html_body=html_body,
                    extra_headers=_build_unsubscribe_headers(unsubscribe_url),
                )
            },
        }
        if configuration_set:
            kwargs["ConfigurationSetName"] = configuration_set
        response = ses_client.send_raw_email(**kwargs)
        return SesSendResult(message_id=response.get("MessageId", ""))
    except Exception as exc:
        logger.exception("SES send failed for %s", recipient)
        return SesSendResult(error=str(exc))
