from django import forms
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from unfold.decorators import display
from unfold.widgets import UnfoldAdminPasswordToggleWidget

from apps.core.models import MicrosoftGraphProviderConfig

from ..common.base import BaseModelAdmin


class WriteOnlySecretField(forms.CharField):
    """A secret that is never shown again, so it only counts as changed when a new value is submitted."""

    def has_changed(self, initial, data):
        return bool((data or "").strip())


class GraphSecretFormMixin:
    """Keep the stored client secret on a blank submit, but never pair it with a different Entra application."""

    def clean_client_secret(self):
        submitted = self.cleaned_data["client_secret"]  # CharField strips, so whitespace-only counts as blank
        self._keeps_stored_secret = not submitted and not self.instance._state.adding
        return submitted or self.instance.client_secret

    def clean(self):
        cleaned = super().clean()
        if getattr(self, "_keeps_stored_secret", False) and {"tenant_id", "client_id"} & set(self.changed_data):
            self.add_error("client_secret", "Enter the client secret for the new application.")
        return cleaned


class MicrosoftGraphProviderConfigForm(GraphSecretFormMixin, forms.ModelForm):
    client_secret = WriteOnlySecretField(
        required=False,
        label="Client Secret",
        widget=UnfoldAdminPasswordToggleWidget(attrs={}, render_value=False),
        help_text="Leave blank when editing to keep the existing client secret.",
    )

    class Meta:
        model = MicrosoftGraphProviderConfig
        fields = ("name", "is_active", "tenant_id", "client_id", "client_secret", "mailbox", "messages_per_minute")


@admin.register(MicrosoftGraphProviderConfig)
class MicrosoftGraphProviderConfigAdmin(BaseModelAdmin):
    form = MicrosoftGraphProviderConfigForm
    list_display = ("name", "status_badge", "mailbox", "client_id", "messages_per_minute", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "mailbox", "client_id")
    ordering = ("-is_active", "-updated_at")
    readonly_fields = ("id", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("name", "is_active")}),
        (_("Entra application"), {"fields": ("tenant_id", "client_id", "client_secret")}),
        (_("Sending"), {"fields": ("mailbox", "messages_per_minute")}),
        (_("Info"), {"fields": ("id", "created_at", "updated_at")}),
    )

    @display(description="Status", label=True)
    def status_badge(self, obj):
        if obj.is_active:
            return "Active", "success"
        return "Inactive", "danger"

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_active:
            return False
        return super().has_delete_permission(request, obj)

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions
