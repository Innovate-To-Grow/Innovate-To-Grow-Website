from django import forms
from django.contrib import admin, messages
from django.contrib.admin.utils import unquote
from django.utils.translation import gettext_lazy as _
from unfold.decorators import display

from apps.core.models import MicrosoftGraphCertificate, MicrosoftGraphProviderConfig
from apps.core.models.base.service_credentials.microsoft_graph import SENDING_LIMIT_FIELDS

from ...common.base import BaseModelAdmin
from .access_check import GraphAccessCheckViewMixin
from .certificate_views import GraphCertificateViewsMixin
from .panel import certificate_panel
from .permissions import GraphPermissionCheckViewMixin, permissions_card, trace_toggle_warning
from .scope import MicrosoftGraphMailboxScopeInline

# The config holds no secret: the certificate's private key is kept in the credential store, and certificates are
# installed, rolled back and removed on their own pages (``GraphCertificateViewsMixin``), never through this form.
GRAPH_FORM_FIELDS = (
    "name",
    "is_active",
    "tenant_id",
    "client_id",
    "mailbox",
    *SENDING_LIMIT_FIELDS,
    "access_check_deny_mailbox",
    "permission_exception_reference",
    "message_trace_enabled",
)
# A certificate is tested for one tenant and app, so these are read-only while one is installed.
APPLICATION_FIELDS = ("tenant_id", "client_id")
# What the go-live gate accepts as evidence: set by whoever runs the access check (the Core app).
EVIDENCE_FIELDS = ("access_check_deny_mailbox", "permission_exception_reference", "message_trace_enabled")
NO_CERTIFICATE = "None installed"


class MicrosoftGraphProviderConfigForm(forms.ModelForm):
    class Meta:
        model = MicrosoftGraphProviderConfig
        fields = GRAPH_FORM_FIELDS


@admin.register(MicrosoftGraphProviderConfig)
class MicrosoftGraphProviderConfigAdmin(
    GraphAccessCheckViewMixin, GraphPermissionCheckViewMixin, GraphCertificateViewsMixin, BaseModelAdmin
):
    form = MicrosoftGraphProviderConfigForm
    inlines = (MicrosoftGraphMailboxScopeInline,)
    change_form_outer_before_template = "admin/core/microsoftgraphproviderconfig/certificate_panel.html"
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
    readonly_fields = ("id", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("name", "is_active")}),
        (
            _("Entra application"),
            {
                "fields": APPLICATION_FIELDS,
                "description": (
                    "Read-only while a certificate is installed: a certificate is tested for one tenant and app. "
                    "To use another app, set up a standby config for it, install its certificate and run the access "
                    "check there, then activate it; while email is sent through Microsoft Graph, activating a config "
                    "needs what switching email to Graph needs."
                ),
            },
        ),
        (
            _("Sending"),
            {
                "fields": ("mailbox",),
                "description": "How fast this mailbox sends and reads is set under Mail → Delivery Rates.",
            },
        ),
        (
            _("Sending limits"),
            {
                "fields": SENDING_LIMIT_FIELDS,
                "description": (
                    "The mailbox's limits as OIT states them. They are the bounds of the Email · Microsoft Graph "
                    "delivery rate (Mail → Delivery Rates): the rate, the Advanced provider rate limit and the daily "
                    "and hourly limits there can be set below these, never above. Raise them here when OIT raises "
                    "the mailbox's limits. Every email the site sends from the mailbox counts against them."
                ),
            },
        ),
        (
            _("Access check and go-live"),
            {
                "fields": EVIDENCE_FIELDS,
                "description": (
                    "The access check (Run access check in the Access check section above, or "
                    "manage.py verify_graph_access from a shell) "
                    "proves against Microsoft that the deny mailbox is refused and that the token's roles are within "
                    "the approval; where the go-live gate is on, email can switch to Microsoft Graph only with a "
                    "recent passing check for the current certificate. Message Trace delivery status needs a tenant-wide "
                    "permission beyond the approval: InfoSec review first, then record its reference here."
                ),
            },
        ),
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
        certificate = obj.current_certificate
        return certificate.sha1_thumbprint if certificate is not None else NO_CERTIFICATE

    @display(description="Valid until")
    def certificate_valid_until(self, obj):
        certificate = obj.current_certificate
        return certificate.not_after if certificate is not None else NO_CERTIFICATE

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is not None and obj.certificates.filter(state__in=MicrosoftGraphCertificate.LIVE_STATES).exists():
            readonly.extend(name for name in APPLICATION_FIELDS if name not in readonly)
        return readonly

    def change_view(self, request, object_id, form_url="", extra_context=None):
        obj = self.get_object(request, unquote(object_id))
        extra_context = dict(extra_context or {})
        if obj is not None:
            panel = certificate_panel(request, obj)
            panel["permissions"] = permissions_card(request, obj)
            extra_context["graph_certificate_panel"] = panel
        return super().change_view(request, object_id, form_url, extra_context)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        warning = trace_toggle_warning(obj) if obj.message_trace_enabled else ""
        if warning:
            messages.warning(request, warning)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_active:
            return False
        return super().has_delete_permission(request, obj)

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    def get_urls(self):
        return (
            self.get_access_check_urls()
            + self.get_permission_check_urls()
            + self.get_certificate_urls()
            + super().get_urls()
        )
