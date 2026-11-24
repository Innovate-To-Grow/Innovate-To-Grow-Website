from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import transaction
from unfold.admin import TabularInline

from apps.core.admin import AppAccessInlineMixin

from ....models import ContactEmail, ContactPhone, Member
from ..contact.phone_verification import ContactPhoneAdminForm, sms_sign_in_status
from ..primary_switch.switch import primary_switch_cell
from ..shared.help_texts import EMAIL_HELP_TEXTS, EMAIL_LABELS
from .fields import UUIDInlineMixin

PRIMARY_EMAIL_INLINE_EDIT_ERROR = (
    "The current primary email's address and type cannot be edited directly. To use another verified address as the "
    "primary, click “Switch primary email” at the top of this page (or “Make primary…” on that address's row). To "
    "correct the primary's address, add the right address as a secondary, have it verified, then switch."
)
PRIMARY_EMAIL_INLINE_DELETE_ERROR = (
    "The current primary email cannot be deleted directly. Switch the primary to another verified address first "
    "(“Switch primary email” at the top of this page), then delete this one."
)
PRIMARY_EMAIL_INLINE_PROMOTION_ERROR = (
    "A primary email cannot be assigned directly. Use “Make primary…” on the address's row (verified addresses only) "
    "or “Switch primary email” at the top of this page."
)
PRIMARY_EMAIL_INLINE_UNVERIFIED_ERROR = (
    "A member's first primary email must be marked verified. An unverified primary email cannot be used to sign in."
)


def _check_new_email_row(form, member_has_primary) -> None:
    # A brand-new row. ProjectControlModel gives every unsaved instance a UUID, so
    # "no persisted row" — not "no pk" — is what identifies one. email_type defaults
    # to "primary", so without this a new row silently became the member's primary
    # while unverified, a state make_contact_email_primary explicitly refuses.
    if form.cleaned_data.get("DELETE", False):
        return
    if form.cleaned_data.get("email_type") == "primary":
        if member_has_primary:
            raise ValidationError(PRIMARY_EMAIL_INLINE_PROMOTION_ERROR)
        if not form.cleaned_data.get("verified", False):
            raise ValidationError(PRIMARY_EMAIL_INLINE_UNVERIFIED_ERROR)


def _check_persisted_email_row(form, persisted) -> None:
    """The primary email is changed only through the dedicated actions, never inline."""
    delete_requested = form.cleaned_data.get("DELETE", False)
    requested_type = form.cleaned_data.get("email_type")
    if requested_type is None and form.is_bound:
        requested_type = form.data.get(form.add_prefix("email_type"))
    requested_type = requested_type or persisted.email_type
    protected_changes = {"email_address", "email_type"}.intersection(form.changed_data)

    if persisted.email_type == "primary":
        if delete_requested:
            raise ValidationError(PRIMARY_EMAIL_INLINE_DELETE_ERROR)
        if protected_changes:
            raise ValidationError(PRIMARY_EMAIL_INLINE_EDIT_ERROR)
    elif requested_type == "primary":
        raise ValidationError(PRIMARY_EMAIL_INLINE_PROMOTION_ERROR)


def _validate_contact_email_rows(formset) -> None:
    # Member is the shared mutex used by the contact-email services.
    # The admin change view already owns an outer transaction, so this
    # lock remains held through save_formset() and prevents a concurrent
    # primary swap from invalidating the checks below.
    member = formset.instance
    if member.pk and not member._state.adding and transaction.get_connection().in_atomic_block:
        Member.objects.select_for_update().get(pk=member.pk)

    persisted_emails = ContactEmail.objects.in_bulk(form.instance.pk for form in formset.forms if form.instance.pk)
    member_has_primary = member.pk and ContactEmail.objects.filter(member=member, email_type="primary").exists()

    for form in formset.forms:
        if not hasattr(form, "cleaned_data"):
            continue
        persisted = persisted_emails.get(form.instance.pk)
        if persisted is None:
            _check_new_email_row(form, member_has_primary)
        else:
            _check_persisted_email_row(form, persisted)

    primary_count = sum(
        1
        for form in formset.forms
        # A form whose own validation failed has no cleaned_data; the loop above already
        # guards for it, so guard here too rather than raising AttributeError.
        if hasattr(form, "cleaned_data")
        and not form.cleaned_data.get("DELETE", False)
        and form.cleaned_data.get("email_type") == "primary"
    )
    if primary_count > 1:
        raise ValidationError("A member may only have one primary email.")


class ContactEmailInlineForm(forms.ModelForm):
    """The member page's contact-email row: the shared labels and help text (shown as "?" in the column headers)."""

    class Meta:
        model = ContactEmail
        fields = "__all__"
        labels = EMAIL_LABELS
        help_texts = EMAIL_HELP_TEXTS


class ContactEmailInline(AppAccessInlineMixin, UUIDInlineMixin, TabularInline):
    """Inline admin for contact email records.

    The primary is switched with "Make primary…" on a verified row (or "Switch primary email" at the top of the page),
    which opens a confirmation page; the row's own type and address never make an address primary.
    """

    model = ContactEmail
    form = ContactEmailInlineForm
    extra = 0
    verbose_name = "Contact Email"
    verbose_name_plural = "Contact Emails"
    fields = ("email_address", "email_type", "verified", "subscribe", "primary_switch", "created_at")
    readonly_fields = ("primary_switch", "created_at")
    # Set per request in get_formset (Django builds new inline instances for every request).
    may_switch_primary = False

    @admin.display(description="Primary email")
    def primary_switch(self, obj):
        return primary_switch_cell(obj, enabled=self.may_switch_primary)

    def get_formset(self, request, obj=None, **kwargs):
        self.may_switch_primary = obj is not None
        formset_class = super().get_formset(request, obj, **kwargs)
        original_clean = formset_class.clean

        def clean(self_fs):
            original_clean(self_fs)
            _validate_contact_email_rows(self_fs)

        formset_class.clean = clean
        return formset_class


class ContactPhoneInline(AppAccessInlineMixin, UUIDInlineMixin, TabularInline):
    """Inline admin for contact phone records.

    ``verified`` can be switched off here but never on: only an SMS code verifies a number, and a changed number
    starts unverified (``ContactPhoneAdminForm``). The SMS sign-in column links unverified numbers to the staff
    "Verify by SMS code" page.
    """

    model = ContactPhone
    form = ContactPhoneAdminForm
    extra = 0
    verbose_name = "Contact Phone"
    verbose_name_plural = "Contact Phones"
    fields = ("phone_number", "region", "verified", "sms_sign_in_status", "subscribe", "created_at")
    readonly_fields = ("sms_sign_in_status", "created_at")

    @admin.display(description="SMS sign-in")
    def sms_sign_in_status(self, obj):
        return sms_sign_in_status(obj)
