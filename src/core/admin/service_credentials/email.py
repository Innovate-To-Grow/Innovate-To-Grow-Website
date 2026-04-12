from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _
from unfold.decorators import action, display
from unfold.widgets import UnfoldAdminPasswordToggleWidget

from core.admin.base import BaseModelAdmin
from core.models import EmailServiceConfig, SMSServiceConfig

from .helpers import _normalize_phone_number, _send_test_email, _send_test_sms


class EmailServiceConfigForm(forms.ModelForm):
    class Meta:
        model = EmailServiceConfig
        fields = "__all__"
        widgets = {
            # First positional arg is `attrs`, not `render_value` — pass attrs explicitly.
            "ses_secret_access_key": UnfoldAdminPasswordToggleWidget(attrs={}, render_value=True),
            "smtp_password": UnfoldAdminPasswordToggleWidget(attrs={}, render_value=True),
        }


@admin.register(EmailServiceConfig)
class EmailServiceConfigAdmin(BaseModelAdmin):
    form = EmailServiceConfigForm
    list_display = ("name", "status_badge", "provider_badge", "ses_from_email", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "ses_from_email", "smtp_host")
    ordering = ("-is_active", "-updated_at")
    actions_detail = ["activate_this_config", "test_send_action"]
    actions_list = ["test_email_list", "test_sms_list"]

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
                    "ses_max_send_rate",
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

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    def get_urls(self):
        custom_urls = [
            path(
                "<path:object_id>/test-send/",
                self.admin_site.admin_view(self.test_send_view),
                name="core_emailserviceconfig_test_send",
            ),
            path(
                "test-email/",
                self.admin_site.admin_view(self.test_email_list_view),
                name="core_emailserviceconfig_test_email",
            ),
            path(
                "test-sms/",
                self.admin_site.admin_view(self.test_sms_list_view),
                name="core_emailserviceconfig_test_sms",
            ),
        ]
        return custom_urls + super().get_urls()

    @action(description="Send test email", url_path="test-send", icon="send")
    def test_send_action(self, request, object_id):
        return HttpResponseRedirect(reverse("admin:core_emailserviceconfig_test_send", args=[object_id]))

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

    @action(description="Test Email", url_path="test-email-action", icon="mail")
    def test_email_list(self, request):
        return HttpResponseRedirect(reverse("admin:core_emailserviceconfig_test_email"))

    @action(description="Test SMS", url_path="test-sms-action", icon="sms")
    def test_sms_list(self, request):
        return HttpResponseRedirect(reverse("admin:core_emailserviceconfig_test_sms"))

    def test_email_list_view(self, request):
        config = EmailServiceConfig.load()
        changelist_url = reverse("admin:core_emailserviceconfig_changelist")

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
            return HttpResponseRedirect(changelist_url)

        context = {
            **self.admin_site.each_context(request),
            "title": f"Send Test Email — {config.name}",
            "input_label": "Recipient email address",
            "input_type": "email",
            "input_placeholder": "admin@example.com",
            "input_help": f"A test email will be sent from {config.source_address} using the active config.",
            "submit_label": "Send Test Email",
            "cancel_url": changelist_url,
        }
        return TemplateResponse(request, "admin/core/test_send_form.html", context)

    def test_sms_list_view(self, request):
        config = SMSServiceConfig.load()
        changelist_url = reverse("admin:core_emailserviceconfig_changelist")

        if request.method == "POST":
            country_code = request.POST.get("country_code", "+1")
            recipient = request.POST.get("recipient", "").strip()
            if not recipient:
                messages.error(request, "Please provide a phone number.")
                return HttpResponseRedirect(request.path)
            full_number = _normalize_phone_number(country_code, recipient)
            try:
                result = _send_test_sms(config=config, phone_number=full_number)
                messages.success(request, f"Test SMS sent to {full_number}: {result} (config: {config.name}).")
            except Exception as exc:
                messages.error(request, f"Failed to send test SMS: {exc}")
            return HttpResponseRedirect(changelist_url)

        context = {
            **self.admin_site.each_context(request),
            "title": f"Send Test SMS — {config.name}",
            "input_label": "Recipient phone number",
            "input_type": "tel",
            "input_placeholder": "2345678901",
            "input_help": "Select country code and enter the phone number.",
            "submit_label": "Send Test SMS",
            "cancel_url": changelist_url,
        }
        return TemplateResponse(request, "admin/core/test_send_form.html", context)
