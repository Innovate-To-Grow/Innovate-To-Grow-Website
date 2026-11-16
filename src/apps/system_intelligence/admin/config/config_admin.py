"""The System Intelligence configuration admin: model, budgets, and which row is active."""

import logging

from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext_lazy as _
from unfold.decorators import action, display

from apps.core.admin.common.base import BaseModelAdmin
from apps.system_intelligence.models import SystemIntelligenceConfig
from apps.system_intelligence.services.public_assistant import global_budget_usage

from .forms import SystemIntelligenceConfigForm

logger = logging.getLogger(__name__)


@admin.register(SystemIntelligenceConfig)
class SystemIntelligenceConfigAdmin(BaseModelAdmin):
    form = SystemIntelligenceConfigForm
    list_display = (
        "name",
        "status_badge",
        "default_model_display",
        "public_assistant_enabled",
        "temperature",
        "max_tokens",
        "updated_at",
    )
    list_filter = ("is_active", "public_assistant_enabled")
    search_fields = ("name",)
    ordering = ("-is_active", "-updated_at")
    actions_detail = ["activate_this_config"]
    fieldsets = (
        (None, {"fields": ("name", "is_active")}),
        (
            _("Model Settings"),
            {
                "fields": ("default_model_id", "temperature", "max_tokens"),
                "description": "Amazon Bedrock model and generation parameters. "
                "Model choices are fetched using the active AWS Credential Config.",
            },
        ),
        (_("System Prompt"), {"fields": ("system_prompt",)}),
        (
            _("Public Assistant"),
            {
                "description": "Public, visitor-facing chatbot. It is tool-free and read-only -- it "
                "never reaches the admin assistant, tools, or private data.",
                "fields": (
                    "public_assistant_enabled",
                    "public_assistant_model_id",
                    "public_assistant_system_prompt",
                    "public_assistant_welcome_message",
                    "public_assistant_starter_questions",
                    "public_assistant_unavailable_message",
                    "public_assistant_temperature",
                    "public_assistant_max_response_tokens",
                    "public_assistant_max_message_chars",
                    "public_assistant_max_history_messages",
                    "public_assistant_ip_token_limit",
                    "public_assistant_ip_token_window_seconds",
                    "public_assistant_global_token_limit",
                    "public_assistant_global_usage",
                    "public_assistant_log_enabled",
                    "public_assistant_log_retention_days",
                ),
            },
        ),
        (_("Info"), {"fields": ("id", "created_at", "updated_at")}),
    )
    readonly_fields = ("id", "created_at", "updated_at", "public_assistant_global_usage")

    @display(description="Status", label=True)
    def status_badge(self, obj):
        return ("Active", "success") if obj.is_active else ("Inactive", "danger")

    @display(description="Global Tokens Used (current window)")
    def public_assistant_global_usage(self, obj):
        """Read-only: how close each feature's global budget is to the limit above.

        The counters are site-wide (one per feature), not per config, and are
        read without locking anything.
        """
        try:
            usage = global_budget_usage()
        except Exception:
            logger.exception("Could not read the assistant global token budget usage.")
            return "Usage is unavailable right now (the budget store could not be read)."
        limit = obj.public_assistant_global_token_limit or 0
        rows = []
        for entry in usage:
            if limit > 0:
                spent = f"{entry.tokens_used:,} of {limit:,} tokens ({entry.tokens_used * 100 // limit}%)"
            else:
                spent = f"{entry.tokens_used:,} tokens; switched off (the limit is 0)"
            if entry.window_expires_at is not None:
                window = f"window ends {timezone.localtime(entry.window_expires_at):%Y-%m-%d %H:%M %Z}"
            elif entry.tokens_used:
                window = "window open"
            else:
                window = "no window open"
            rows.append((entry.label, spent, window))
        note = (
            "Each feature has its own counter. Reserved tokens of calls in flight are included."
            if obj.is_active
            else "Each feature has its own counter. This config is not active: the counters are site-wide and "
            "the active config's limit is the one enforced."
        )
        return format_html(
            "{}<div>{}</div>",
            format_html_join("", "<div><strong>{}:</strong> {} &middot; {}</div>", rows),
            note,
        )

    @display(description="Default Model")
    def default_model_display(self, obj):
        if not obj.default_model_id:
            return "—"
        try:
            from apps.system_intelligence.services.bedrock import get_available_models

            match = next(
                (
                    name
                    for _group, models in get_available_models()
                    for mid, name in models
                    if mid == obj.default_model_id
                ),
                None,
            )
            if match is not None:
                return match
        except Exception:
            logger.exception(
                "Failed to resolve default model display name for System Intelligence config '%s'.", obj.pk
            )
        return obj.default_model_id

    @action(description="Activate this config", url_path="activate", icon="check_circle")
    def activate_this_config(self, request, object_id):
        obj = SystemIntelligenceConfig.objects.get(pk=object_id)
        obj.is_active = True
        obj.save()
        messages.success(request, f'"{obj.name}" is now the active System Intelligence config.')
        return HttpResponseRedirect(
            reverse("admin:system_intelligence_systemintelligenceconfig_change", args=[object_id])
        )

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_active:
            return False
        return super().has_delete_permission(request, obj)

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions
