from django.urls import reverse

from apps.core.models import (
    EmailServiceConfig,
    GmailApiProviderConfig,
    MicrosoftGraphProviderConfig,
)
from apps.core.utils.access import user_can_access_app

Provider = EmailServiceConfig.Provider


def _details(config, aws_config, smtp_config) -> dict[str, str]:
    graph = MicrosoftGraphProviderConfig.load()
    return {
        Provider.SES: f"Region {aws_config.region}" if aws_config.ses_configured else "",
        Provider.SMTP: f"{smtp_config.host}:{smtp_config.port}" if smtp_config.is_configured else "",
        Provider.GRAPH: f"Mailbox {graph.sender_mailbox(config.from_email)}" if graph.is_configured else "",
        Provider.GMAIL: f"Sends as {config.from_email}" if GmailApiProviderConfig.load().is_configured else "",
    }


def _configure_url(request, provider: str) -> str:
    """Where this viewer sets the provider up, or "" when that needs access the viewer does not have."""
    if provider == Provider.SES:
        return reverse("admin:mail_settings_edit")
    if provider == Provider.SMTP:
        if user_can_access_app(request.user, "core"):
            return reverse("admin:core_smtpproviderconfig_changelist")
        return reverse("admin:mail_settings_edit")
    if provider == Provider.GRAPH:
        can_manage = user_can_access_app(request.user, "core")
        return reverse("admin:core_microsoftgraphproviderconfig_changelist") if can_manage else ""
    can_manage = user_can_access_app(request.user, "core")
    return reverse("admin:core_gmailapiproviderconfig_changelist") if can_manage else ""
