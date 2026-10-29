from django import forms
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from unfold.admin import TabularInline
from unfold.decorators import display
from unfold.widgets import UnfoldAdminPasswordToggleWidget

from apps.core.models import MicrosoftGraphMailboxScope, MicrosoftGraphProviderConfig

from ..common.base import BaseModelAdmin

GRAPH_FORM_FIELDS = (
    "name",
    "is_active",
    "tenant_id",
    "client_id",
    "auth_method",
    "certificate",
    "private_key",
    "client_secret",
    "mailbox",
    "messages_per_minute",
)


class WriteOnlyTextarea(forms.Textarea):
    """A multi-line secret input that never renders a value: neither the stored key nor a rejected submission."""

    def format_value(self, value):
        return None


class WriteOnlySecretField(forms.CharField):
    """A secret that is never shown again, so it only counts as changed when a new value is submitted."""

    def has_changed(self, initial, data):
        return bool((data or "").strip())


class GraphSecretFormMixin:
    """Keep stored secrets on a blank submit, but never pair them with a different Entra application."""

    def setup_write_only_fields(self):
        self._kept_secrets = set()
        self.fields["client_secret"] = WriteOnlySecretField(
            required=False,
            label="Client Secret",
            widget=UnfoldAdminPasswordToggleWidget(attrs={}, render_value=False),
            help_text="Leave blank to keep the existing client secret. Used only with the client secret method.",
        )
        self.fields["private_key"] = WriteOnlySecretField(
            required=False,
            label="Private Key (PEM)",
            widget=WriteOnlyTextarea(attrs={"rows": 4, "autocomplete": "off", "spellcheck": "false"}),
            help_text=(
                "Unencrypted RSA private key of the certificate (-----BEGIN PRIVATE KEY-----). It is stored like "
                "the other service credentials and never shown again; leave blank when editing to keep it."
            ),
        )

    def _clean_write_only(self, name):
        submitted = (self.cleaned_data.get(name) or "").strip()  # whitespace-only counts as blank
        if not submitted and not self.instance._state.adding and getattr(self.instance, name):
            self._kept_secrets.add(name)
        return submitted or getattr(self.instance, name)

    def clean_client_secret(self):
        return self._clean_write_only("client_secret")

    def clean_private_key(self):
        return self._clean_write_only("private_key")

    def clean(self):
        cleaned = super().clean()
        if {"tenant_id", "client_id"} & set(self.changed_data):
            for name in self._kept_secrets:
                label = "client secret" if name == "client_secret" else "private key"
                self.add_error(name, f"Enter the {label} for the new application.")
        return cleaned


class MicrosoftGraphProviderConfigForm(GraphSecretFormMixin, forms.ModelForm):
    class Meta:
        model = MicrosoftGraphProviderConfig
        fields = GRAPH_FORM_FIELDS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_write_only_fields()


class MicrosoftGraphMailboxScopeInline(TabularInline):
    model = MicrosoftGraphMailboxScope
    fields = ("mailbox", "permission")
    extra = 0
    verbose_name = "Mailbox in scope"
    verbose_name_plural = "Mailbox scope (only these mailboxes may be used, with these permissions)"


@admin.register(MicrosoftGraphProviderConfig)
class MicrosoftGraphProviderConfigAdmin(BaseModelAdmin):
    form = MicrosoftGraphProviderConfigForm
    inlines = (MicrosoftGraphMailboxScopeInline,)
    list_display = (
        "name",
        "status_badge",
        "client_id",
        "auth_method",
        "mailbox",
        "scope_summary",
        "certificate_expires_at",
        "updated_at",
    )
    list_filter = ("is_active", "auth_method")
    search_fields = ("name", "mailbox", "client_id")
    ordering = ("-is_active", "-updated_at")
    readonly_fields = ("certificate_thumbprint", "certificate_expires_at", "id", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("name", "is_active")}),
        (_("Entra application"), {"fields": ("tenant_id", "client_id", "auth_method")}),
        (
            _("Certificate"),
            {
                "fields": ("certificate", "private_key", "certificate_thumbprint", "certificate_expires_at"),
                "description": "Used when Authentication is Certificate. Upload the same certificate to the Entra app.",
            },
        ),
        (_("Client secret"), {"fields": ("client_secret",), "classes": ("collapse",)}),
        (_("Sending"), {"fields": ("mailbox", "messages_per_minute")}),
        (_("Info"), {"fields": ("id", "created_at", "updated_at")}),
    )

    @display(description="Status", label=True)
    def status_badge(self, obj):
        if obj.is_active:
            return "Active", "success"
        return "Inactive", "danger"

    @display(description="Mailbox scope")
    def scope_summary(self, obj):
        return ", ".join(str(scope) for scope in obj.mailbox_scopes.all()) or "— (nothing allowed)"

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_active:
            return False
        return super().has_delete_permission(request, obj)

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions
