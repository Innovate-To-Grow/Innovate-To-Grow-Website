"""What the active email configuration sends with: its From address and whether delivery is configured."""

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from ..gmail_api import GmailApiProviderConfig
from ..microsoft_graph import MicrosoftGraphProviderConfig
from .smtp import SMTPProviderConfig


class EmailDeliveryStatusMixin:
    """Delivery properties for ``EmailServiceConfig``."""

    @property
    def source_address(self):
        """Formatted sender address for email headers."""
        if self.from_name:
            return f"{self.from_name} <{self.from_email}>"
        return self.from_email

    @property
    def ses_configured(self):
        """SES requires both an active sender row and active AWS credentials."""
        from apps.core.models import AWSCredentialConfig

        return bool(
            self.pk
            and self.is_active
            and self.provider == self.Provider.SES
            and self.from_email
            and AWSCredentialConfig.load().ses_configured
        )

    @property
    def delivery_summary(self):
        """Where mail goes right now, for admin panels: ``AWS SES (us-west-2)``, ``SMTP (host:587)``, ..."""
        if not self.delivery_configured:
            return "Not configured"
        if self.provider == self.Provider.SMTP:
            smtp = SMTPProviderConfig.load()
            return f"SMTP ({smtp.host}:{smtp.port})"
        if self.provider == self.Provider.GRAPH:
            graph = MicrosoftGraphProviderConfig.load()
            return f"Microsoft Graph ({graph.mailbox or self.from_email})"
        if self.provider == self.Provider.GMAIL:
            return f"Gmail API ({self.from_email})"
        from apps.core.models import AWSCredentialConfig

        return f"AWS SES ({AWSCredentialConfig.load().region or 'us-west-2'})"

    @property
    def delivery_configured(self):
        """Return whether the selected provider is structurally ready."""
        if not (self.pk and self.is_active and self.from_email):
            return False
        try:
            validate_email(self.from_email)
        except ValidationError:
            return False
        if self.provider == self.Provider.SES:
            return self.ses_configured
        if self.provider == self.Provider.SMTP:
            return SMTPProviderConfig.load().is_configured
        if self.provider == self.Provider.GRAPH:
            return MicrosoftGraphProviderConfig.load().sending_ready(self.from_email)
        if self.provider == self.Provider.GMAIL:
            # Readiness only: editing the allow-list or rotating the key never stops mail that can be sent.
            return GmailApiProviderConfig.load().sending_ready(self.from_email)
        return False
