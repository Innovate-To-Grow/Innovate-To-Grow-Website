from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from unfold.decorators import action, display
from unfold.widgets import UnfoldAdminTextareaWidget

from core.admin.base import BaseModelAdmin
from core.models.base.system_intelligence import SystemIntelligenceActionRequest, SystemIntelligenceConfig


class SystemIntelligenceConfigForm(forms.ModelForm):
    class Meta:
        model = SystemIntelligenceConfig
        fields = "__all__"
        widgets = {"system_prompt": UnfoldAdminTextareaWidget(attrs={"rows": 8})}


@admin.register(SystemIntelligenceConfig)
class SystemIntelligenceConfigAdmin(BaseModelAdmin):
    form = SystemIntelligenceConfigForm
    list_display = ("name", "status_badge", "temperature", "max_tokens", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name",)
    ordering = ("-is_active", "-updated_at")
    actions_detail = ["activate_this_config"]
    fieldsets = (
        (None, {"fields": ("name", "is_active")}),
        (
            _("Model Settings"),
            {
                "fields": ("temperature", "max_tokens"),
                "description": "Amazon Bedrock generation parameters. Model defaults from AWS Credential Config.",
            },
        ),
        (_("System Prompt"), {"fields": ("system_prompt",)}),
        (_("Info"), {"fields": ("updated_at",)}),
    )
    readonly_fields = ("updated_at",)

    @display(description="Status", label=True)
    def status_badge(self, obj):
        return ("Active", "success") if obj.is_active else ("Inactive", "danger")

    @action(description="Activate this config", url_path="activate", icon="check_circle")
    def activate_this_config(self, request, object_id):
        obj = SystemIntelligenceConfig.objects.get(pk=object_id)
        obj.is_active = True
        obj.save()
        messages.success(request, f'"{obj.name}" is now the active System Intelligence config.')
        return HttpResponseRedirect(reverse("admin:core_systemintelligenceconfig_change", args=[object_id]))

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
