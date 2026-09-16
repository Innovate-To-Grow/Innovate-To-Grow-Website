from django import forms
from django.contrib import admin
from django.utils.html import format_html, format_html_join
from unfold.widgets import UnfoldAdminPasswordToggleWidget

from apps.authn.services.send_verification.config import load_settings
from apps.authn.services.send_verification.constants import ALLOWED_ALGORITHMS
from apps.authn.services.send_verification.exceptions import SendVerificationUnavailable
from apps.core.models import SendVerificationConfig

from ..common.base import BaseModelAdmin


class SendVerificationConfigForm(forms.ModelForm):
    def clean(self):
        cleaned = super().clean()
        if cleaned.get("algorithm") and cleaned["algorithm"] not in ALLOWED_ALGORITHMS:
            self.add_error("algorithm", "Use a supported algorithm: " + ", ".join(sorted(ALLOWED_ALGORITHMS)))
        for name, minimum in (("cost", 1), ("challenge_ttl_seconds", 30), ("destination_hourly_limit", 1)):
            value = cleaned.get(name)
            if value is not None and value < minimum:
                self.add_error(name, f"Enter a value of at least {minimum}.")
        return cleaned

    class Meta:
        model = SendVerificationConfig
        fields = (
            "name",
            "is_active",
            "mode",
            "hmac_secret",
            "hmac_key_secret",
            "hmac_secret_previous",
            "hmac_key_secret_previous",
            "key_version",
            "algorithm",
            "cost",
            "challenge_ttl_seconds",
            "destination_hourly_limit",
            "destination_cooldown_seconds",
            "sms_daily_limit",
        )
        widgets = {
            "hmac_secret": UnfoldAdminPasswordToggleWidget(attrs={}, render_value=True),
            "hmac_key_secret": UnfoldAdminPasswordToggleWidget(attrs={}, render_value=True),
            "hmac_secret_previous": UnfoldAdminPasswordToggleWidget(attrs={}, render_value=True),
            "hmac_key_secret_previous": UnfoldAdminPasswordToggleWidget(attrs={}, render_value=True),
        }


@admin.register(SendVerificationConfig)
class SendVerificationConfigAdmin(BaseModelAdmin):
    form = SendVerificationConfigForm
    list_display = ("name", "is_active", "mode", "key_version", "updated_at")
    list_filter = ("is_active", "mode")
    ordering = ("-is_active", "-updated_at")
    fieldsets = (
        (None, {"fields": ("name", "is_active", "mode")}),
        (
            "Effective configuration",
            {
                "fields": ("effective_configuration",),
                "description": (
                    "Current saved runtime values. Explicit environment/settings overrides win over the active "
                    "configuration, then defaults apply. Pause in either source always stops protected sends. "
                    "Save and reload to see policy changes take effect. Secret values are never displayed here."
                ),
            },
        ),
        (
            "Secrets",
            {
                "fields": (
                    "hmac_secret",
                    "hmac_key_secret",
                    "hmac_secret_previous",
                    "hmac_key_secret_previous",
                    "key_version",
                ),
                "description": "Rotate by moving the current secrets into Previous, then saving new values.",
            },
        ),
        (
            "Policy",
            {
                "fields": (
                    "algorithm",
                    "cost",
                    "challenge_ttl_seconds",
                    "destination_hourly_limit",
                    "destination_cooldown_seconds",
                    "sms_daily_limit",
                )
            },
        ),
        ("Info", {"fields": ("updated_at",)}),
    )
    readonly_fields = ("updated_at", "effective_configuration")

    @admin.display(description="Values and sources")
    def effective_configuration(self, obj):
        try:
            config = load_settings()
        except SendVerificationUnavailable as exc:
            return format_html("<p>Invalid effective configuration; protected sends are blocked. {}</p>", exc.detail)
        rows = []
        for name, source in config.sources.items():
            value = getattr(config, name)
            if "secret" in name:
                value = "Configured" if value else "Not configured"
            elif name == "sms_daily_limit" and value is None:
                value = "Not calibrated (SMS blocked in enforce mode)"
            rows.append((name.replace("_", " ").capitalize(), value, source))
        return format_html(
            "<table><thead><tr><th>Setting</th><th>Effective value</th><th>Source</th></tr></thead><tbody>{}</tbody></table>",
            format_html_join("", "<tr><th>{}</th><td>{}</td><td>{}</td></tr>", rows),
        )
