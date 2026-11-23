"""The AI provider admin: endpoints other than Amazon Bedrock that System Intelligence can call."""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from unfold.decorators import display

from apps.core.admin.common.base import BaseModelAdmin
from apps.system_intelligence.models import LLMProviderConfig

from .provider_keys import ProviderKeyActionsMixin


@admin.register(LLMProviderConfig)
class LLMProviderConfigAdmin(ProviderKeyActionsMixin, BaseModelAdmin):
    list_display = ("name", "preset", "endpoint_display", "status_badge", "key_display", "updated_at")
    list_filter = ("preset", "is_enabled")
    search_fields = ("name",)
    fieldsets = (
        (
            None,
            {
                "fields": ("name", "preset", "is_enabled"),
                "description": "Install the API key with the Install API key action, test it, then enable the "
                "provider and select it in the System Intelligence Config.",
            },
        ),
        (_("Custom endpoint"), {"fields": ("api_format", "base_url")}),
        (_("Limits"), {"fields": ("request_timeout_seconds", "context_window_tokens")}),
        (_("API key"), {"fields": ("key_display", "key_installed_at")}),
        (_("Info"), {"fields": ("id", "created_at", "updated_at")}),
    )
    readonly_fields = ("id", "created_at", "updated_at", "key_display", "key_installed_at")

    # A provider receives everything its role sends (staff chats, tool results, inbox mail), so only the I2G Master
    # (superuser) may add, change, key, test or delete one; other System Intelligence staff can only view them.
    def has_add_permission(self, request):
        return request.user.is_superuser and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser and super().has_delete_permission(request, obj)

    @display(description="Status", label=True)
    def status_badge(self, obj):
        return ("Enabled", "success") if obj.is_enabled else ("Disabled", "danger")

    @display(description="Endpoint")
    def endpoint_display(self, obj):
        return f"{obj.get_api_format_display() if obj.is_custom else ''} {obj.effective_base_url}".strip() or "—"

    @display(description="API Key")
    def key_display(self, obj):
        return f"Installed (ends …{obj.key_hint})" if obj.key_configured else "Not installed"
