import logging
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from django.conf import settings

from apps.core.models import EmailServiceConfig
from apps.core.services.aws.credentials import AwsCredentialsError, resolve_aws_credentials
from apps.core.services.aws.provider_outcomes import (
    NO_PROVIDER_RETRIES,
    PROVIDER_OUTCOME_PERMANENT,
    PROVIDER_OUTCOME_SUCCESS,
    PROVIDER_OUTCOME_TRANSIENT,
    PROVIDER_OUTCOME_UNCERTAIN,
    classify_aws_send_failure,
)

logger = logging.getLogger(__name__)

SES_OUTCOME_SUCCESS = PROVIDER_OUTCOME_SUCCESS
SES_OUTCOME_TRANSIENT = PROVIDER_OUTCOME_TRANSIENT
SES_OUTCOME_PERMANENT = PROVIDER_OUTCOME_PERMANENT
SES_OUTCOME_UNCERTAIN = PROVIDER_OUTCOME_UNCERTAIN


@dataclass
class SesSendResult:
    """Outcome of a single SES send_raw_email call."""

    message_id: str = ""
    error: str = ""
    provider: str = "ses"
    outcome: str = ""

    def __post_init__(self):
        if not self.outcome:
            self.outcome = SES_OUTCOME_UNCERTAIN if self.error else SES_OUTCOME_SUCCESS


def _get_ses_client(config):
    if not config.ses_configured:
        return None
    try:
        import boto3

        creds = resolve_aws_credentials("ses")
        return boto3.client(
            "ses",
            region_name=creds.region,
            aws_access_key_id=creds.access_key_id,
            aws_secret_access_key=creds.secret_access_key,
            config=NO_PROVIDER_RETRIES,
        )
    except AwsCredentialsError:
        logger.warning("SES client not built: AWS credentials are not configured")
        return None
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
        logger.exception("SES send failed")
        outcome, error = _classify_ses_failure(exc)
        return SesSendResult(error=error, outcome=outcome)


def _classify_ses_failure(exc: Exception) -> tuple[str, str]:
    """Classify whether a failed SES call is safe to retry or may have landed."""
    return classify_aws_send_failure(exc, provider="SES")
