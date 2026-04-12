from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from unfold.decorators import action, display
from unfold.widgets import UnfoldAdminPasswordToggleWidget

from core.admin.base import BaseModelAdmin
from core.models import GmailImportConfig


class GmailImportConfigForm(forms.ModelForm):
    class Meta:
        model = GmailImportConfig
        fields = "__all__"
        widgets = {
            "gmail_password": UnfoldAdminPasswordToggleWidget(attrs={}, render_value=True),
        }


@admin.register(GmailImportConfig)
class GmailImportConfigAdmin(BaseModelAdmin):
    form = GmailImportConfigForm
    list_display = ("name", "status_badge", "imap_host", "gmail_username", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "gmail_username", "imap_host")
    ordering = ("-is_active", "-updated_at")
    actions_detail = ["activate_this_config"]

    fieldsets = (
        (
            None,
            {"fields": ("name", "is_active")},
        ),
        (
            _("Gmail IMAP"),
            {
                "fields": ("imap_host", "gmail_username", "gmail_password"),
                "description": "Credentials used to read recent sent Gmail templates over IMAP.",
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

    @action(description="Activate this config", url_path="activate", icon="check_circle")
    def activate_this_config(self, request, object_id):
        obj = GmailImportConfig.objects.get(pk=object_id)
        obj.is_active = True
        obj.save()
        messages.success(request, f'"{obj.name}" is now the active Gmail import config.')
        return HttpResponseRedirect(reverse("admin:core_gmailimportconfig_change", args=[object_id]))

    # noinspection PyUnusedLocal,PyMethodMayBeStatic
    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_active:
            return False
        return super().has_delete_permission(request, obj)

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions
