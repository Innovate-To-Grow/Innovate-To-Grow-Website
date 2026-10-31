from django import forms
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from unfold.admin import TabularInline
from unfold.decorators import display

from apps.core.models import MicrosoftGraphMailboxScope, MicrosoftGraphProviderConfig

from ..common.base import BaseModelAdmin

# The config holds no secret: the certificate's private key is kept in the credential store, and certificates are
# installed, rolled back and removed through the credential lifecycle, never through this form.
GRAPH_FORM_FIELDS = (
    "name",
    "is_active",
    "tenant_id",
    "client_id",
    "mailbox",
    "messages_per_minute",
)
NO_CERTIFICATE = "None installed"


class MicrosoftGraphProviderConfigForm(forms.ModelForm):
    class Meta:
        model = MicrosoftGraphProviderConfig
        fields = GRAPH_FORM_FIELDS


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
        "mailbox",
        "scope_summary",
        "certificate_thumbprint",
        "certificate_valid_until",
        "updated_at",
    )
    list_filter = ("is_active",)
    search_fields = ("name", "mailbox", "client_id")
    ordering = ("-is_active", "-updated_at")
    readonly_fields = (
        "certificate_thumbprint",
        "certificate_sha256",
        "certificate_subject",
        "certificate_valid_from",
        "certificate_valid_until",
        "certificate_key_version",
        "certificate_entra_check",
        "previous_certificate_summary",
        "id",
        "created_at",
        "updated_at",
    )
    fieldsets = (
        (None, {"fields": ("name", "is_active")}),
        (_("Entra application"), {"fields": ("tenant_id", "client_id")}),
        (
            _("Certificate"),
            {
                "fields": (
                    "certificate_thumbprint",
                    "certificate_sha256",
                    "certificate_subject",
                    "certificate_valid_from",
                    "certificate_valid_until",
                    "certificate_key_version",
                    "certificate_entra_check",
                    "previous_certificate_summary",
                ),
                "description": (
                    "The app authenticates with a certificate only. Its private key is kept in the credential "
                    "store (AWS Secrets Manager in production) and is never stored or shown here. Compare the "
                    "SHA-1 thumbprint with the one Entra lists under Certificates & secrets."
                ),
            },
        ),
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

    @display(description="Thumbprint (SHA-1)")
    def certificate_thumbprint(self, obj):
        return self._current(obj, "sha1_thumbprint")

    @display(description="SHA-256 fingerprint")
    def certificate_sha256(self, obj):
        return self._current(obj, "sha256_fingerprint")

    @display(description="Subject")
    def certificate_subject(self, obj):
        return self._current(obj, "subject")

    @display(description="Valid from")
    def certificate_valid_from(self, obj):
        return self._current(obj, "not_before")

    @display(description="Valid until")
    def certificate_valid_until(self, obj):
        return self._current(obj, "not_after")

    @display(description="Key store version")
    def certificate_key_version(self, obj):
        return self._current(obj, "store_version_id")

    @display(description="Entra check")
    def certificate_entra_check(self, obj):
        certificate = obj.current_certificate if obj else None
        if certificate is None:
            return NO_CERTIFICATE
        code = f" ({certificate.entra_check_code})" if certificate.entra_check_code else ""
        return f"{certificate.get_entra_check_display()}{code}, {certificate.entra_checked_at:%Y-%m-%d %H:%M} UTC"

    @display(description="Previous certificate (rollback)")
    def previous_certificate_summary(self, obj):
        certificate = obj.previous_certificate if obj else None
        return str(certificate) if certificate is not None else "None"

    @staticmethod
    def _current(obj, attribute):
        certificate = obj.current_certificate if obj else None
        return getattr(certificate, attribute) if certificate is not None else NO_CERTIFICATE

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_active:
            return False
        return super().has_delete_permission(request, obj)

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions
