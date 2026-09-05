from django import forms
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from unfold.decorators import display
from unfold.widgets import UnfoldAdminPasswordToggleWidget

from apps.core.models import SMTPProviderConfig

from ..common.base import BaseModelAdmin


class SMTPProviderConfigForm(forms.ModelForm):
    password = forms.CharField(
        required=False,
        widget=UnfoldAdminPasswordToggleWidget(attrs={}, render_value=False),
        help_text="Leave blank when editing to keep the existing password.",
    )

    class Meta:
        model = SMTPProviderConfig
        fields = (
            "name",
            "is_active",
            "host",
            "port",
            "use_tls",
            "use_ssl",
            "username",
            "password",
            "timeout",
        )

    def clean_password(self):
        password = self.cleaned_data["password"]
        if not password and self.instance.pk:
            return self.instance.password
        return password


@admin.register(SMTPProviderConfig)
class SMTPProviderConfigAdmin(BaseModelAdmin):
    form = SMTPProviderConfigForm
    list_display = ("name", "status_badge", "host", "port", "security", "updated_at")
    list_filter = ("is_active", "use_tls", "use_ssl")
    search_fields = ("name", "host", "username")
    ordering = ("-is_active", "-updated_at")
    readonly_fields = ("id", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("name", "is_active")}),
        (_("Connection"), {"fields": ("host", "port", "use_tls", "use_ssl", "timeout")}),
        (_("Authentication"), {"fields": ("username", "password")}),
        (_("Info"), {"fields": ("id", "created_at", "updated_at")}),
    )

    @display(description="Status", label=True)
    def status_badge(self, obj):
        if obj.is_active:
            return "Active", "success"
        return "Inactive", "danger"

    @display(description="Security")
    def security(self, obj):
        if obj.use_ssl:
            return "SSL"
        if obj.use_tls:
            return "TLS"
        return "None"

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_active:
            return False
        return super().has_delete_permission(request, obj)

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions
