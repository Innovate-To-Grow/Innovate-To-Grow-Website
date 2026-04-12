from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from unfold.decorators import action, display
from unfold.widgets import UnfoldAdminPasswordToggleWidget

from core.admin.base import BaseModelAdmin
from core.models import AWSCredentialConfig


class AWSCredentialConfigForm(forms.ModelForm):
    class Meta:
        model = AWSCredentialConfig
        fields = "__all__"
        widgets = {
            "secret_access_key": UnfoldAdminPasswordToggleWidget(attrs={}, render_value=True),
        }


@admin.register(AWSCredentialConfig)
class AWSCredentialConfigAdmin(BaseModelAdmin):
    form = AWSCredentialConfigForm
    list_display = ("name", "status_badge", "configured_badge", "access_key_id", "default_region", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "access_key_id")
    ordering = ("-is_active", "-updated_at")
    actions_detail = ["activate_this_config"]

    fieldsets = (
        (
            None,
            {"fields": ("name", "is_active")},
        ),
        (
            _("AWS Credentials"),
            {
                "fields": ("access_key_id", "secret_access_key", "default_region"),
                "description": "IAM access key used by AWS services (SES, S3, etc.).",
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

    @display(description="Configured", label=True)
    def configured_badge(self, obj):
        if obj.is_configured:
            return "Yes", "success"
        return "No", "warning"

    @action(description="Activate this config", url_path="activate", icon="check_circle")
    def activate_this_config(self, request, object_id):
        obj = AWSCredentialConfig.objects.get(pk=object_id)
        obj.is_active = True
        obj.save()
        messages.success(request, f'"{obj.name}" is now the active AWS credential config.')
        return HttpResponseRedirect(reverse("admin:core_awscredentialconfig_change", args=[object_id]))

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_active:
            return False
        return super().has_delete_permission(request, obj)

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions
