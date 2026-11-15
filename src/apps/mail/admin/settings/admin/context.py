from django.contrib import admin
from django.urls import reverse

from apps.core.admin.service_credentials.gmail_api.panel import key_panel
from apps.core.admin.service_credentials.microsoft_graph.panel import certificate_panel
from apps.core.models import (
    GmailApiProviderConfig,
)
from apps.core.utils.access import user_can_access_app
from apps.mail.services.campaign.pacing import email_send_rate_line, sms_send_rate_line

from ..rate_cards import EMAIL_CHANNELS


def _graph_context(request, graph_config) -> dict:
    """The active Graph config, read-only: it is managed on its own admin page, which needs the Core app."""
    saved = not graph_config._state.adding
    context = {
        "graph_saved": saved,
        "graph_scopes": list(graph_config.mailbox_scopes.all()) if saved else [],
        "graph_certificate_panel": certificate_panel(request, graph_config, actions=False),
        "graph_admin_url": "",
    }
    if user_can_access_app(request.user, "core"):
        context["graph_admin_url"] = (
            reverse("admin:core_microsoftgraphproviderconfig_change", args=[graph_config.pk])
            if saved
            else reverse("admin:core_microsoftgraphproviderconfig_add")
        )
    return context


def _gmail_context(request) -> dict:
    """The active Gmail API config, read-only and without any credential field: it is managed on its own admin
    page, which needs the Core app (like the other provider configs)."""
    gmail_config = GmailApiProviderConfig.load()
    saved = not gmail_config._state.adding
    admin_url = ""
    if user_can_access_app(request.user, "core"):
        admin_url = (
            reverse("admin:core_gmailapiproviderconfig_change", args=[gmail_config.pk])
            if saved
            else reverse("admin:core_gmailapiproviderconfig_add")
        )
    return {
        "gmail_config": gmail_config,
        "gmail_saved": saved,
        "gmail_key_panel": key_panel(request, gmail_config, actions=False),
        "gmail_admin_url": admin_url,
    }


def _notification_delivery_context(request, email_config, aws_config, smtp_config, graph_config):
    email_provider, email_provider_color = _email_provider_state(email_config, aws_config, smtp_config, graph_config)
    sms_provider, sms_provider_color = _sms_provider_state(aws_config)
    return {
        **admin.site.each_context(request),
        "title": "Notification Delivery",
        "config": email_config,
        "aws_config": aws_config,
        "smtp_config": smtp_config,
        "graph_config": graph_config,
        **_graph_context(request, graph_config),
        **_gmail_context(request),
        "email_status": "Active" if email_config.is_active else "Inactive",
        "email_send_rate": email_send_rate_line(),
        "aws_status": "Active" if aws_config.is_active else "Inactive",
        "masked_access_key": "Secrets Manager"
        if aws_config.credentials_secret_arn
        else _mask_key(aws_config.access_key_id),
        "secret_key_status": "Configured" if aws_config.is_configured else "Not configured",
        "resolved_sms_number": aws_config.resolved_sms_from_number(),
        # After the number is resolved: an auto-detected number is known to the limiter once it is cached.
        "sms_send_rate": sms_send_rate_line(),
        "sms_number_is_override": bool(aws_config.sms_from_number),
        "sms_template_display": aws_config.sms_message_template or "Default OTP message",
        "email_provider": email_provider,
        "email_provider_color": email_provider_color,
        "sms_provider": sms_provider,
        "sms_provider_color": sms_provider_color,
        "test_email_url": reverse("admin:mail_settings_test_email"),
        "test_sms_url": reverse("admin:mail_settings_test_sms"),
        "delivery_rates_url": reverse("admin:mail_delivery_rates"),
        "email_rate_channel": EMAIL_CHANNELS.get(email_config.provider, ""),
    }


def _mask_key(value):
    if not value:
        return "Not configured"
    return f"...{value[-4:]}"


def _email_provider_state(email_config, aws_config, smtp_config, graph_config):
    if email_config.provider == "smtp":
        if smtp_config.is_configured:
            return f"SMTP ({smtp_config.host}:{smtp_config.port})", "success"
        return "SMTP not configured", "warning"
    if email_config.provider == "graph":
        if graph_config.is_configured:
            return f"Microsoft Graph ({graph_config.mailbox or email_config.from_email})", "success"
        return "Microsoft Graph not configured", "warning"
    if email_config.provider == "gmail":
        if GmailApiProviderConfig.load().sending_ready(email_config.from_email):
            return f"Gmail API ({email_config.from_email})", "success"
        return "Gmail API not configured", "warning"
    if aws_config.ses_configured:
        return f"Amazon Simple Email Service ({aws_config.region})", "success"
    return "Amazon Simple Email Service not configured", "warning"


def _sms_provider_state(aws_config):
    if aws_config.sns_configured:
        return f"Amazon Simple Notification Service ({aws_config.region})", "success"
    return "Amazon Simple Notification Service not configured", "warning"
