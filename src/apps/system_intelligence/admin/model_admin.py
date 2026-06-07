import logging

from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from unfold.decorators import action, display
from unfold.widgets import UnfoldAdminSelectWidget, UnfoldAdminTextareaWidget

from apps.core.admin.base import BaseModelAdmin
from apps.system_intelligence.models import SystemIntelligenceActionRequest, SystemIntelligenceConfig

logger = logging.getLogger(__name__)


class SystemIntelligenceConfigForm(forms.ModelForm):
    default_model_id = forms.TypedChoiceField(
        coerce=str,
        required=False,
        label="Default AI Model",
        help_text="Site-wide default Bedrock model or inference profile ID.",
        widget=UnfoldAdminSelectWidget,
    )
    public_assistant_model_id = forms.TypedChoiceField(
        coerce=str,
        required=False,
        label="Public Assistant Model",
        help_text="Bedrock model/inference profile ID for the public assistant. Falls back to the Default AI Model.",
        widget=UnfoldAdminSelectWidget,
    )

    class Meta:
        model = SystemIntelligenceConfig
        fields = "__all__"
        widgets = {
            "system_prompt": UnfoldAdminTextareaWidget(attrs={"rows": 8}),
            "public_assistant_system_prompt": UnfoldAdminTextareaWidget(attrs={"rows": 8}),
            "public_assistant_unavailable_message": UnfoldAdminTextareaWidget(attrs={"rows": 3}),
            "public_assistant_welcome_message": UnfoldAdminTextareaWidget(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._populate_model_choices("default_model_id", empty_label="---------")
        self._populate_model_choices("public_assistant_model_id", empty_label="Use Default AI Model")

    def _populate_model_choices(self, field_name, *, empty_label):
        """Populate a model-id field with the live Bedrock catalog, grouped by provider."""
        current = self.initial.get(field_name, "") or getattr(self.instance, field_name, "") or ""
        try:
            from apps.core.services.bedrock import get_available_models

            grouped = get_available_models()
            choices = [("", empty_label)]
            seen_model_ids = set()
            for group, models in grouped:
                seen_model_ids.update(model_id for model_id, _name in models)
                choices.append((group, list(models)))
            if current and current not in seen_model_ids:
                choices.append(("Configured Model", [(current, current)]))
            self.fields[field_name].choices = choices
        except Exception:
            logger.debug("Could not fetch Bedrock models for System Intelligence config choices", exc_info=True)
            if current:
                self.fields[field_name].choices = [("", empty_label), (current, current)]
            else:
                self.fields[field_name].choices = [("", empty_label)]


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
                    "public_assistant_log_enabled",
                    "public_assistant_log_retention_days",
                ),
            },
        ),
        (_("Info"), {"fields": ("id", "created_at", "updated_at")}),
    )
    readonly_fields = ("id", "created_at", "updated_at")

    @display(description="Status", label=True)
    def status_badge(self, obj):
        return ("Active", "success") if obj.is_active else ("Inactive", "danger")

    @display(description="Default Model")
    def default_model_display(self, obj):
        if not obj.default_model_id:
            return "—"
        try:
            from apps.core.services.bedrock import get_available_models

            for _group, models in get_available_models():
                for mid, name in models:
                    if mid == obj.default_model_id:
                        return name
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


@admin.register(SystemIntelligenceActionRequest)
class SystemIntelligenceActionRequestAdmin(BaseModelAdmin):
    list_display = ("title", "action_type", "status", "target_model", "target_pk", "created_by", "created_at")
    list_filter = ("status", "action_type", "target_app_label", "target_model")
    search_fields = ("title", "summary", "target_repr", "target_pk")
    ordering = ("-created_at",)
    readonly_fields = (
        "id",
        "conversation",
        "assistant_message",
        "created_by",
        "reviewed_by",
        "action_type",
        "status",
        "target_app_label",
        "target_model",
        "target_pk",
        "target_repr",
        "title",
        "summary",
        "payload",
        "before_snapshot",
        "after_snapshot",
        "diff",
        "preview_token",
        "preview_url",
        "preview_expires_at",
        "error_message",
        "created_at",
        "updated_at",
        "reviewed_at",
        "applied_at",
    )
    fieldsets = (
        (None, {"fields": ("id", "title", "summary", "action_type", "status")}),
        (_("Target"), {"fields": ("target_app_label", "target_model", "target_pk", "target_repr")}),
        (_("Conversation"), {"fields": ("conversation", "assistant_message", "created_by", "reviewed_by")}),
        (_("Preview"), {"fields": ("preview_url", "preview_token", "preview_expires_at")}),
        (_("Payload and Audit"), {"fields": ("payload", "before_snapshot", "after_snapshot", "diff", "error_message")}),
        (_("Timestamps"), {"fields": ("created_at", "updated_at", "reviewed_at", "applied_at")}),
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
