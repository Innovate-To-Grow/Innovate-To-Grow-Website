"""The admin of the actions the assistant asked to take."""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from apps.core.admin.common.base import BaseModelAdmin
from apps.core.utils.access import user_can_access_app
from apps.system_intelligence.models import ChatConversation, SystemIntelligenceActionRequest
from apps.system_intelligence.services.actions.engine.tool_access import has_chat_grants


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

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset
        grants = getattr(request.user, "admin_apps", None) or []
        conversations = ChatConversation.objects.filter(created_by=request.user)
        restricted = [
            pk
            for pk, required_apps in conversations.values_list("pk", "required_tool_apps")
            if not has_chat_grants(request.user, required_apps)
        ]
        return queryset.filter(
            conversation__created_by=request.user,
            target_app_label__in=[grant for grant in grants if user_can_access_app(request.user, grant)],
        ).exclude(conversation_id__in=restricted)

    def has_delete_permission(self, request, obj=None):
        return False
