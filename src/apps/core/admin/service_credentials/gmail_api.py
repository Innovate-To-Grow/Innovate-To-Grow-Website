"""The Gmail API provider config in the admin: superusers only, change form, account allow-list and key pages.

Everything here defines the Gmail credential or how far it reaches (which Workspace users the site may impersonate),
so every permission is superuser-only, unlike the Core app's other pages. The config holds no secret: the key is
installed and removed on its own pages (``GmailApiKeyViewsMixin``), never through this form.
"""

from django import forms
from django.contrib import admin
from django.contrib.admin.utils import unquote
from django.db.models.constants import LOOKUP_SEP
from django.forms.models import BaseInlineFormSet
from django.utils.translation import gettext_lazy as _
from unfold.admin import TabularInline
from unfold.decorators import display

from apps.core.models import EmailServiceConfig, GmailApiProviderConfig, GmailApiSubject
from apps.core.models.base.service_credentials.gmail_api import normalize_subject

from ..common.base import BaseModelAdmin
from .gmail_api_panel import key_panel
from .gmail_api_views import GmailApiKeyViewsMixin

KEY_FACTS = (
    "service_account_email",
    "client_id",
    "key_id",
    "project_id",
    "key_installed_at",
    "access_checked_at",
)
# Changelist filters: only these. Anything else (the store pointer, the key facts, the allow-list) could be probed
# one guess at a time through the result count.
ALLOWED_LOOKUPS = frozenset({"is_active", "credential_mail"})
ALLOW_LIST_HELP = (
    "Only these Google accounts may be impersonated, and mail is sent only From one of them. Google cannot restrict "
    "domain-wide delegation per user (\"OAuth scopes don't restrict which users the service account can "
    'impersonate"), so this list is the only per-user control, and it protects only against site errors, not '
    "against someone holding the key."
)
WOULD_STOP_EMAIL = (
    "Mail → Notification Delivery sends email through the Gmail API From {from_email}, so this change would stop "
    "all email: the active configuration must keep that address on its allow-list. Switch Notification Delivery to "
    "another provider first if you need to make this change."
)


class SuperuserOnlyMixin:
    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    def has_add_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser


class SubjectInlineForm(forms.ModelForm):
    class Meta:
        model = GmailApiSubject
        fields = ("subject",)

    def clean_subject(self):
        # Normalised here too, so the formset's duplicate check compares the stored form.
        return normalize_subject(self.cleaned_data.get("subject"))


class SubjectFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        email = EmailServiceConfig.load()
        if email.provider != EmailServiceConfig.Provider.GMAIL or not email.delivery_configured:
            return
        if not GmailApiProviderConfig.objects.filter(pk=self.instance.pk, is_active=True).exists():
            return  # a standby: email does not depend on it
        kept = {
            form.cleaned_data.get("subject")
            for form in self.forms
            if getattr(form, "cleaned_data", None) and not (self.can_delete and self._should_delete_form(form))
        }
        if normalize_subject(email.from_email) not in kept:
            raise forms.ValidationError(WOULD_STOP_EMAIL.format(from_email=email.from_email))


class GmailApiSubjectInline(SuperuserOnlyMixin, TabularInline):
    model = GmailApiSubject
    form = SubjectInlineForm
    formset = SubjectFormSet
    fields = ("subject", "verified_at")
    readonly_fields = ("verified_at",)
    extra = 0
    verbose_name = "Google account"
    verbose_name_plural = "Account allow-list (only these accounts may be impersonated and sent From)"

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        formset.help_text = ALLOW_LIST_HELP
        return formset


class GmailApiProviderConfigForm(forms.ModelForm):
    class Meta:
        model = GmailApiProviderConfig
        fields = ("name", "is_active", "max_recipients_per_message", "max_message_bytes", "credential_mail")


@admin.register(GmailApiProviderConfig)
class GmailApiProviderConfigAdmin(SuperuserOnlyMixin, GmailApiKeyViewsMixin, BaseModelAdmin):
    form = GmailApiProviderConfigForm
    inlines = (GmailApiSubjectInline,)
    change_form_outer_before_template = "admin/core/gmailapiproviderconfig/key_panel.html"
    list_display = ("name", "status_badge", "service_account_email", "key_id", "allow_list", "updated_at")
    list_filter = ("is_active",)
    ordering = ("-is_active", "-updated_at")
    readonly_fields = ("id", "created_at", "updated_at", *KEY_FACTS)
    fieldsets = (
        (None, {"fields": ("name", "is_active")}),
        (
            _("Installed key"),
            {
                "fields": KEY_FACTS,
                "description": (
                    "Public facts of the installed service-account key. The key itself is in the credential store "
                    "and is installed or removed with the buttons above. The Workspace super admin authorizes the "
                    "numeric Client ID for exactly https://www.googleapis.com/auth/gmail.send."
                ),
            },
        ),
        (
            _("Sending"),
            {
                "fields": ("credential_mail", "max_recipients_per_message", "max_message_bytes"),
                "description": "How fast this account sends, and its daily limits, are set under Mail → Delivery Rates.",
            },
        ),
        (_("Info"), {"fields": ("id", "created_at", "updated_at")}),
    )

    @display(description="Status", label=True)
    def status_badge(self, obj):
        return ("Active", "success") if obj.is_active else ("Inactive", "danger")

    @display(description="Allow-list")
    def allow_list(self, obj):
        return ", ".join(obj.subjects.values_list("subject", flat=True)) or "— (nothing allowed)"

    def lookup_allowed(self, lookup, value, request=None):
        if str(lookup).split(LOOKUP_SEP, 1)[0] not in ALLOWED_LOOKUPS:
            return False
        return super().lookup_allowed(lookup, value, request)

    def get_search_fields(self, request):
        return ()

    def change_view(self, request, object_id, form_url="", extra_context=None):
        obj = self.get_object(request, unquote(object_id))
        extra_context = dict(extra_context or {})
        if obj is not None:
            extra_context["gmail_key_panel"] = key_panel(request, obj)
        return super().change_view(request, object_id, form_url, extra_context)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_active:
            return False
        return super().has_delete_permission(request, obj)

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    def get_urls(self):
        return self.get_key_urls() + super().get_urls()
