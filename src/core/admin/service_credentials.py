from django import forms
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin

from core.models import EmailServiceConfig, SMSServiceConfig


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

    fieldsets = (
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

    def has_add_permission(self, request):
        if EmailServiceConfig.objects.exists():
            return False
        return super().has_add_permission(request)

    # noinspection PyUnusedLocal,PyMethodMayBeStatic
    def has_delete_permission(self, request, obj=None):
        return False


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

    fieldsets = (
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

    def has_add_permission(self, request):
        if SMSServiceConfig.objects.exists():
            return False
        return super().has_add_permission(request)

    # noinspection PyUnusedLocal,PyMethodMayBeStatic
    def has_delete_permission(self, request, obj=None):
        return False
