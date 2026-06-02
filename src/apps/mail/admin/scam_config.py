from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from unfold.decorators import action, display

from apps.core.admin.base import BaseModelAdmin
from apps.mail.models import ScamDetectorConfig


@admin.register(ScamDetectorConfig)
class ScamDetectorConfigAdmin(BaseModelAdmin):
    list_display = ("name", "status_badge", "medium_threshold", "high_threshold", "ai_review_enabled", "updated_at")
    list_filter = ("is_active", "ai_review_enabled")
    search_fields = ("name",)
    ordering = ("-is_active", "-updated_at")
    actions_detail = ["activate_this_config"]
    fieldsets = (
        (None, {"fields": ("name", "is_active")}),
        ("Risk thresholds", {"fields": ("medium_threshold", "high_threshold")}),
        ("Tuning", {"fields": ("extra_brands", "trusted_senders")}),
        ("AI review", {"fields": ("ai_review_enabled", "ai_review_band")}),
        ("Info", {"fields": ("id", "created_at", "updated_at")}),
    )
    readonly_fields = ("id", "created_at", "updated_at")

    @display(description="Status", label=True)
    def status_badge(self, obj):
        return ("Active", "success") if obj.is_active else ("Inactive", "danger")

    @action(description="Activate this config", url_path="activate", icon="check_circle")
    def activate_this_config(self, request, object_id):
        obj = ScamDetectorConfig.objects.get(pk=object_id)
        obj.is_active = True
        obj.save()
        messages.success(request, f'"{obj.name}" is now the active scam detector config.')
        return HttpResponseRedirect(reverse("admin:mail_scamdetectorconfig_change", args=[object_id]))

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_active:
            return False
        return super().has_delete_permission(request, obj)

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions
