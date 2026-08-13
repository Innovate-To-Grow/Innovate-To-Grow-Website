"""AWS SES email provider."""

import boto3
from botocore.config import Config

from apps.core.services.aws.credentials import AwsCredentialsError, resolve_aws_credentials
from apps.core.services.aws.provider_outcomes import classify_aws_send_failure

from .contracts import DeliveryResult, EmailMessage
from .exceptions import PermanentEmailDeliveryError, TransientEmailDeliveryError, UncertainEmailDeliveryError
from .mime import build_mime_message

_ERROR_TYPES = {
    "permanent": PermanentEmailDeliveryError,
    "transient": TransientEmailDeliveryError,
    "uncertain": UncertainEmailDeliveryError,
}


class SESProvider:
    """Deliver raw MIME messages through SES using explicit DB credentials."""

    name = "ses"

    def __init__(
        self,
        *,
        from_email: str,
        from_name: str = "",
        configuration_set: str | None = None,
        retry_config: Config | None = None,
    ):
        self.from_email = from_email
        self.from_name = from_name
        self.configuration_set = configuration_set
        self.retry_config = retry_config

    def send(self, message: EmailMessage, *, before_provider_call=None) -> DeliveryResult:
        mime = build_mime_message(message, from_email=self.from_email, from_name=self.from_name)
        try:
            credentials = resolve_aws_credentials("ses")
            client_options = {
                "region_name": credentials.region,
                "aws_access_key_id": credentials.access_key_id,
                "aws_secret_access_key": credentials.secret_access_key,
            }
            if self.retry_config is not None:
                client_options["config"] = self.retry_config
            client = boto3.client("ses", **client_options)
            kwargs = {
                "Source": self.from_email,
                "Destinations": list(message.envelope_recipients),
                "RawMessage": {"Data": mime.as_bytes()},
            }
            if self.configuration_set:
                kwargs["ConfigurationSetName"] = self.configuration_set
        except AwsCredentialsError as exc:
            raise PermanentEmailDeliveryError("AWS SES credentials are not configured.") from exc
        except Exception as exc:
            outcome, detail = classify_aws_send_failure(exc, provider="AWS SES")
            raise _ERROR_TYPES[outcome](detail) from exc

        if before_provider_call is not None:
            before_provider_call()
        try:
            response = client.send_raw_email(**kwargs)
        except Exception as exc:
            outcome, detail = classify_aws_send_failure(exc, provider="AWS SES")
            raise _ERROR_TYPES[outcome](detail) from exc

        message_id = response.get("MessageId")
        if not message_id:
            raise UncertainEmailDeliveryError("AWS SES accepted the request without returning a message ID.")
        return DeliveryResult(provider=self.name, message_id=message_id)
