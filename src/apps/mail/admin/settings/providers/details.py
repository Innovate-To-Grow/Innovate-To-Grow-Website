from django.urls import reverse

from apps.core.models import (
    EmailServiceConfig,
    GmailApiProviderConfig,
    MicrosoftGraphProviderConfig,
)

Provider = EmailServiceConfig.Provider


def _details(config, aws_config, smtp_config) -> dict[str, str]:
    graph = MicrosoftGraphProviderConfig.load()
    return {
        Provider.SES: f"Region {aws_config.region}" if aws_config.ses_configured else "",
        Provider.SMTP: f"{smtp_config.host}:{smtp_config.port}" if smtp_config.is_configured else "",
        Provider.GRAPH: f"Mailbox {graph.sender_mailbox(config.from_email)}" if graph.is_configured else "",
        Provider.GMAIL: f"Sends as {config.from_email}" if GmailApiProviderConfig.load().is_configured else "",
    }


CONFIGURE_URL_NAMES = {
    Provider.SES: "admin:mail_settings_edit",
    Provider.SMTP: "admin:core_smtpproviderconfig_changelist",
    Provider.GRAPH: "admin:core_microsoftgraphproviderconfig_changelist",
    Provider.GMAIL: "admin:core_gmailapiproviderconfig_changelist",
}


def _configure_url(provider: str) -> str:
    """Where the provider is set up."""
    return reverse(CONFIGURE_URL_NAMES[provider])
