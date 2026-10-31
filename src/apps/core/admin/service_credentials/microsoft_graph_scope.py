"""The mailbox scope inline on the Graph config page, and the guard that keeps the selected email provider working.

Mail → Notification Delivery checks a provider before selecting it; this guard is the other direction. While the
active email config sends through Microsoft Graph and works, a save on the Graph config page may not leave it
unable to send: deactivating the sending config, activating a standby that cannot send, or a mailbox scope or
sender mailbox that no longer lets the sender and the From address send. The check runs in the inline formset's
``clean()``, after the config form has applied its values, so it sees the config and the scope as they would be
saved and nothing is written when it fails.
"""

from django import forms
from django.forms.models import BaseInlineFormSet
from unfold.admin import TabularInline

from apps.core.models import EmailServiceConfig, MicrosoftGraphMailboxScope, MicrosoftGraphProviderConfig
from apps.core.models.base.service_credentials.microsoft_graph import normalize_mailbox

from ..common.base import AppAccessInlineMixin

WOULD_STOP_EMAIL = (
    "Mail → Notification Delivery sends email through Microsoft Graph with this configuration, so this change "
    "would stop all email. The sending configuration must stay active, keep a valid certificate, and keep a "
    "mailbox scope that lets the sender mailbox and the From address ({from_email}) send. Switch Notification "
    "Delivery to another provider first if you need to make this change."
)


def email_stop_reason(config, scopes: dict) -> str:
    """Why saving *config* with mailbox *scopes* ({mailbox: permission}) would stop email that works now, or ""."""
    email = EmailServiceConfig.load()
    if email.provider != EmailServiceConfig.Provider.GRAPH or not email.delivery_configured:
        return ""
    sending_pk = MicrosoftGraphProviderConfig.objects.filter(is_active=True).values_list("pk", flat=True).first()
    if config.pk != sending_pk and not config.is_active:
        return ""  # a standby that stays a standby
    if config.sending_ready(email.from_email, scopes=scopes):
        return ""
    return WOULD_STOP_EMAIL.format(from_email=email.from_email)


class MailboxScopeInlineForm(forms.ModelForm):
    class Meta:
        model = MicrosoftGraphMailboxScope
        fields = ("mailbox", "permission")

    def clean_mailbox(self):
        # Normalised here, not only in the model, so the formset's duplicate check compares the stored form:
        # "I2G@x.edu" and "i2g@x.edu" are one mailbox, and two rows for it would fail the unique constraint.
        return normalize_mailbox(self.cleaned_data.get("mailbox"))


class MailboxScopeFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        scopes = {}
        for form in self.forms:
            data = getattr(form, "cleaned_data", None) or {}
            if data.get("mailbox") and not (self.can_delete and self._should_delete_form(form)):
                scopes[data["mailbox"]] = data.get("permission")
        reason = email_stop_reason(self.instance, scopes)
        if reason:
            raise forms.ValidationError(reason)


class MicrosoftGraphMailboxScopeInline(AppAccessInlineMixin, TabularInline):
    """Editable by staff granted the Core app, like the config itself (``AppAccessInlineMixin``)."""

    model = MicrosoftGraphMailboxScope
    form = MailboxScopeInlineForm
    formset = MailboxScopeFormSet
    fields = ("mailbox", "permission")
    extra = 0
    verbose_name = "Mailbox in scope"
    verbose_name_plural = "Mailbox scope (only these mailboxes may be used, with these permissions)"
