from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from django.conf import settings

from apps.core.models import EmailServiceConfig
from apps.core.services.aws.provider_outcomes import (
    NO_PROVIDER_RETRIES,
    PROVIDER_OUTCOME_PERMANENT,
    PROVIDER_OUTCOME_SUCCESS,
    PROVIDER_OUTCOME_TRANSIENT,
    PROVIDER_OUTCOME_UNCERTAIN,
)
from apps.core.services.email import EmailDeliveryError, EmailMessage, deliver_email

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
    return config if config.delivery_configured else None


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
    before_provider_call=None,
) -> SesSendResult:
    del source
    try:
        result = deliver_email(
            EmailMessage(
                subject=subject,
                to=(recipient,),
                html_body=html_body,
                headers=_build_unsubscribe_headers(unsubscribe_url),
            ),
            config=ses_client,
            retry_config=NO_PROVIDER_RETRIES,
            configuration_set=configuration_set,
            before_provider_call=before_provider_call,
        )
        return SesSendResult(message_id=result.message_id, provider=result.provider, outcome=result.outcome)
    except EmailDeliveryError as exc:
        return SesSendResult(error=str(exc), provider=getattr(ses_client, "provider", ""), outcome=exc.outcome)


def _classify_ses_failure(exc: Exception) -> tuple[str, str]:
    """Classify whether a failed SES call is safe to retry or may have landed."""
    if isinstance(exc, EmailDeliveryError):
        return exc.outcome, str(exc)
    return PROVIDER_OUTCOME_UNCERTAIN, "Email provider request outcome could not be confirmed."
