"""Provider-neutral email delivery facade."""

from .contracts import DeliveryResult, EmailMessage
from .exceptions import PermanentEmailDeliveryError
from .registry import resolve_provider


class EmailDeliveryService:
    """Deliver through one explicitly configured provider."""

    def __init__(self, config: object | None = None):
        if config is None:
            from apps.core.models import EmailServiceConfig

            config = EmailServiceConfig.load()
        self.config = config

    def send(self, message: EmailMessage, *, before_provider_call=None, **provider_options) -> DeliveryResult:
        if not getattr(self.config, "is_active", False):
            raise PermanentEmailDeliveryError("No active email service configuration exists.")
        provider = resolve_provider(self.config, **provider_options)
        return provider.send(message, before_provider_call=before_provider_call)


def deliver_email(
    message: EmailMessage,
    *,
    config: object | None = None,
    before_provider_call=None,
    retry_config=None,
    configuration_set: str | None = None,
) -> DeliveryResult:
    """Deliver one message through the active or supplied configuration."""
    return EmailDeliveryService(config).send(
        message,
        before_provider_call=before_provider_call,
        retry_config=retry_config,
        configuration_set=configuration_set,
    )
