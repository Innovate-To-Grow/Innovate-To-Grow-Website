"""Mail settings admin views."""

from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from unfold.widgets import UnfoldAdminPasswordToggleWidget

from core.admin.service_credentials.helpers import _send_test_email
from core.models import AWSCredentialConfig, EmailServiceConfig


class MailSettingsForm(forms.ModelForm):
    class Meta:
        model = EmailServiceConfig
        fields = (
            "name",
            "is_active",
            "ses_from_name",
            "ses_from_email",
            "ses_max_send_rate",
            "smtp_host",
            "smtp_port",
            "smtp_use_tls",
            "smtp_username",
            "smtp_password",
        )
        widgets = {
            "smtp_password": UnfoldAdminPasswordToggleWidget(attrs={}, render_value=True),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        input_class = "w-full rounded-md border border-base-300 px-3 py-2 text-sm"
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "rounded border-base-300")
                continue
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} {input_class}".strip()


def get_mail_settings_urls():
    return [
        path("mail/settings/", admin.site.admin_view(mail_settings_view), name="mail_settings"),
        path(
            "mail/settings/test-email/",
            admin.site.admin_view(mail_settings_test_email_view),
            name="mail_settings_test_email",
        ),
    ]


def mail_settings_view(request):
    config = EmailServiceConfig.load()
    if request.method == "POST":
        form = MailSettingsForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, "Mail settings saved.")
            return HttpResponseRedirect(reverse("admin:mail_settings"))
    else:
        form = MailSettingsForm(instance=config)

    provider, provider_color = _provider_state(config)
    context = {
        **admin.site.each_context(request),
        "title": "Mail Settings",
        "form": form,
        "sender_fields": [
            form[name] for name in ("name", "is_active", "ses_from_name", "ses_from_email", "ses_max_send_rate")
        ],
        "gmail_fields": [
            form[name] for name in ("smtp_host", "smtp_port", "smtp_use_tls", "smtp_username", "smtp_password")
        ],
        "config": config,
        "provider": provider,
        "provider_color": provider_color,
        "aws_config": AWSCredentialConfig.load(),
        "test_email_url": reverse("admin:mail_settings_test_email"),
    }
    return TemplateResponse(request, "admin/mail/settings.html", context)


def mail_settings_test_email_view(request):
    config = EmailServiceConfig.load()
    settings_url = reverse("admin:mail_settings")

    if request.method == "POST":
        recipient = request.POST.get("recipient", "").strip()
        if not recipient:
            messages.error(request, "Please provide a recipient email address.")
            return HttpResponseRedirect(request.path)
        try:
            provider = _send_test_email(config=config, recipient=recipient)
            messages.success(request, f"Test email sent to {recipient} via {provider} (config: {config.name}).")
        except Exception as exc:
            messages.error(request, f"Failed to send test email: {exc}")
        return HttpResponseRedirect(settings_url)

    context = {
        **admin.site.each_context(request),
        "title": f"Send Test Email - {config.name}",
        "input_label": "Recipient email address",
        "input_type": "email",
        "input_placeholder": "admin@example.com",
        "input_help": f"A test email will be sent from {config.source_address} using the active mail settings.",
        "submit_label": "Send Test Email",
        "cancel_url": settings_url,
    }
    return TemplateResponse(request, "admin/core/test_send_form.html", context)


def _provider_state(config):
    aws_config = AWSCredentialConfig.load()
    if aws_config.ses_configured:
        return f"AWS IAM ({aws_config.region})", "success"
    if config.smtp_configured:
        return f"Gmail ({config.smtp_host})", "info"
    return "Not configured", "warning"
