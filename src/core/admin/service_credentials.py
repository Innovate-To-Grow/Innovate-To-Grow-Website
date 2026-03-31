import logging

from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.decorators import action, display

from core.models import EmailServiceConfig, SMSServiceConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------


class EmailServiceConfigForm(forms.ModelForm):
    class Meta:
        model = EmailServiceConfig
        fields = "__all__"
        widgets = {
            "ses_secret_access_key": forms.PasswordInput(render_value=True),
            "smtp_password": forms.PasswordInput(render_value=True),
        }


@admin.register(EmailServiceConfig)
class EmailServiceConfigAdmin(ModelAdmin):
    form = EmailServiceConfigForm
    list_display = ("name", "status_badge", "provider_badge", "ses_from_email", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "ses_from_email", "smtp_host")
    ordering = ("-is_active", "-updated_at")
    actions_detail = ["activate_this_config", "test_send_action"]

    fieldsets = (
        (
            None,
            {"fields": ("name", "is_active")},
        ),
        (
            _("AWS SES (Primary)"),
            {
                "fields": (
                    "ses_access_key_id",
                    "ses_secret_access_key",
                    "ses_region",
                    "ses_from_email",
                    "ses_from_name",
                ),
                "description": "Leave Access Key blank to skip SES and use SMTP only.",
            },
        ),
        (
            _("SMTP (Fallback)"),
            {
                "fields": (
                    "smtp_host",
                    "smtp_port",
                    "smtp_use_tls",
                    "smtp_username",
                    "smtp_password",
                ),
            },
        ),
        (_("Info"), {"fields": ("updated_at",)}),
    )
    readonly_fields = ("updated_at",)

    @display(description="Status", label=True)
    def status_badge(self, obj):
        if obj.is_active:
            return "Active", "success"
        return "Inactive", "danger"

    @display(description="Provider", label=True)
    def provider_badge(self, obj):
        if obj.ses_access_key_id:
            return "SES + SMTP", "info"
        return "SMTP only", "warning"

    @action(description="Activate this config", url_path="activate", icon="check_circle")
    def activate_this_config(self, request, object_id):
        obj = EmailServiceConfig.objects.get(pk=object_id)
        obj.is_active = True
        obj.save()
        messages.success(request, f'"{obj.name}" is now the active email config.')
        return HttpResponseRedirect(reverse("admin:core_emailserviceconfig_change", args=[object_id]))

    # noinspection PyUnusedLocal,PyMethodMayBeStatic
    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_active:
            return False
        return super().has_delete_permission(request, obj)

    def get_urls(self):
        custom_urls = [
            path(
                "<path:object_id>/test-send/",
                self.admin_site.admin_view(self.test_send_view),
                name="core_emailserviceconfig_test_send",
            ),
        ]
        return custom_urls + super().get_urls()

    @action(description="Send test email", url_path="test-send", icon="send")
    def test_send_action(self, request, object_id):
        return HttpResponseRedirect(
            reverse("admin:core_emailserviceconfig_test_send", args=[object_id])
        )

    def test_send_view(self, request, object_id):
        obj = EmailServiceConfig.objects.get(pk=object_id)
        change_url = reverse("admin:core_emailserviceconfig_change", args=[object_id])

        if request.method == "POST":
            recipient = request.POST.get("recipient", "").strip()
            if not recipient:
                messages.error(request, "Please provide a recipient email address.")
                return HttpResponseRedirect(request.path)
            try:
                provider = _send_test_email(config=obj, recipient=recipient)
                messages.success(request, f"Test email sent to {recipient} via {provider}.")
            except Exception as exc:
                messages.error(request, f"Failed to send test email: {exc}")
            return HttpResponseRedirect(change_url)

        context = {
            **self.admin_site.each_context(request),
            "title": f"Send Test Email — {obj.name}",
            "input_label": "Recipient email address",
            "input_type": "email",
            "input_placeholder": "admin@example.com",
            "input_help": f"A test email will be sent from {obj.source_address}.",
            "submit_label": "Send Test Email",
            "cancel_url": change_url,
        }
        return TemplateResponse(request, "admin/core/test_send_form.html", context)


# ---------------------------------------------------------------------------
# SMS
# ---------------------------------------------------------------------------


class SMSServiceConfigForm(forms.ModelForm):
    class Meta:
        model = SMSServiceConfig
        fields = "__all__"
        widgets = {
            "auth_token": forms.PasswordInput(render_value=True),
        }


@admin.register(SMSServiceConfig)
class SMSServiceConfigAdmin(ModelAdmin):
    form = SMSServiceConfigForm
    list_display = ("name", "status_badge", "account_sid", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "account_sid")
    ordering = ("-is_active", "-updated_at")
    actions_detail = ["activate_this_config", "test_send_action"]

    fieldsets = (
        (
            None,
            {"fields": ("name", "is_active")},
        ),
        (
            _("Twilio Verify"),
            {
                "fields": ("account_sid", "auth_token", "verify_sid"),
                "description": "Twilio credentials for SMS phone verification (Verify API).",
            },
        ),
        (_("Info"), {"fields": ("updated_at",)}),
    )
    readonly_fields = ("updated_at",)

    @display(description="Status", label=True)
    def status_badge(self, obj):
        if obj.is_active:
            return "Active", "success"
        return "Inactive", "danger"

    @action(description="Activate this config", url_path="activate", icon="check_circle")
    def activate_this_config(self, request, object_id):
        obj = SMSServiceConfig.objects.get(pk=object_id)
        obj.is_active = True
        obj.save()
        messages.success(request, f'"{obj.name}" is now the active SMS config.')
        return HttpResponseRedirect(reverse("admin:core_smsserviceconfig_change", args=[object_id]))

    # noinspection PyUnusedLocal,PyMethodMayBeStatic
    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_active:
            return False
        return super().has_delete_permission(request, obj)

    def get_urls(self):
        custom_urls = [
            path(
                "<path:object_id>/test-send/",
                self.admin_site.admin_view(self.test_send_view),
                name="core_smsserviceconfig_test_send",
            ),
        ]
        return custom_urls + super().get_urls()

    @action(description="Send test SMS", url_path="test-send", icon="send")
    def test_send_action(self, request, object_id):
        return HttpResponseRedirect(
            reverse("admin:core_smsserviceconfig_test_send", args=[object_id])
        )

    def test_send_view(self, request, object_id):
        obj = SMSServiceConfig.objects.get(pk=object_id)
        change_url = reverse("admin:core_smsserviceconfig_change", args=[object_id])

        if request.method == "POST":
            recipient = request.POST.get("recipient", "").strip()
            if not recipient:
                messages.error(request, "Please provide a phone number.")
                return HttpResponseRedirect(request.path)
            try:
                _send_test_sms(config=obj, phone_number=recipient)
                messages.success(request, f"Test SMS sent to {recipient}.")
            except Exception as exc:
                messages.error(request, f"Failed to send test SMS: {exc}")
            return HttpResponseRedirect(change_url)

        context = {
            **self.admin_site.each_context(request),
            "title": f"Send Test SMS — {obj.name}",
            "input_label": "Recipient phone number",
            "input_type": "tel",
            "input_placeholder": "+1234567890",
            "input_help": "Include country code (e.g. +1 for US). A Twilio Verify code will be sent.",
            "submit_label": "Send Test SMS",
            "cancel_url": change_url,
        }
        return TemplateResponse(request, "admin/core/test_send_form.html", context)


# ---------------------------------------------------------------------------
# Helpers — test send
# ---------------------------------------------------------------------------


def _send_test_email(*, config, recipient):
    """Send a test email using the given EmailServiceConfig. Returns provider name."""
    subject = "Test Email — Innovate to Grow Admin"
    html_body = (
        "<h2>Test Email</h2>"
        "<p>This is a test email sent from the I2G admin panel.</p>"
        "<p>Your email service configuration is working correctly.</p>"
    )

    if config.ses_configured:
        try:
            import boto3

            client = boto3.client(
                "ses",
                region_name=config.ses_region,
                aws_access_key_id=config.ses_access_key_id,
                aws_secret_access_key=config.ses_secret_access_key,
            )
            client.send_email(
                Destination={"ToAddresses": [recipient]},
                Message={
                    "Body": {"Html": {"Charset": "UTF-8", "Data": html_body}},
                    "Subject": {"Charset": "UTF-8", "Data": subject},
                },
                Source=config.source_address,
            )
            return "SES"
        except Exception:
            logger.exception("SES test send failed for %s", recipient)

    from django.core.mail import EmailMessage, get_connection

    connection = get_connection(
        host=config.smtp_host,
        port=config.smtp_port,
        username=config.smtp_username,
        password=config.smtp_password,
        use_tls=config.smtp_use_tls,
        fail_silently=False,
    )
    msg = EmailMessage(
        subject=subject,
        body=html_body,
        from_email=config.source_address,
        to=[recipient],
        connection=connection,
    )
    msg.content_subtype = "html"
    msg.send()
    return "SMTP"


def _send_test_sms(*, config, phone_number):
    """Send a test SMS verification using the given SMSServiceConfig."""
    if not config.is_configured:
        raise ValueError("Twilio credentials are not fully configured.")

    from twilio.rest import Client

    client = Client(config.account_sid, config.auth_token)
    verification = client.verify.v2.services(config.verify_sid).verifications.create(
        to=phone_number, channel="sms"
    )
    return verification.status
