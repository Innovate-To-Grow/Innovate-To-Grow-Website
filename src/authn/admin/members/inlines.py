from django import forms
from django.core.exceptions import ValidationError
from django.forms.models import InlineForeignKeyField
from unfold.admin import TabularInline

from ...models import ContactEmail, ContactPhone


class NoneSafeUUIDField(forms.UUIDField):
    """UUIDField that treats the literal string "None" as empty."""

    def to_python(self, value):
        if value in (None, "None", ""):
            return None
        return super().to_python(value)


class NoneSafeModelChoiceField(forms.ModelChoiceField):
    """ModelChoiceField that treats the literal string "None" as empty."""

    def to_python(self, value):
        if value in (None, "None", ""):
            return None
        return super().to_python(value)


class NoneSafeInlineForeignKeyField(InlineForeignKeyField):
    """Inline parent FK field that treats the literal string "None" as empty."""

    def clean(self, value):
        if value == "None":
            value = None
        return super().clean(value)


class StaffPermissionInlineMixin:
    """Grant full inline permissions to any staff user, matching BaseModelAdmin."""

    def has_view_permission(self, request, obj=None):
        return request.user.is_staff

    def has_add_permission(self, request, obj=None):
        return request.user.is_staff

    def has_change_permission(self, request, obj=None):
        return request.user.is_staff

    def has_delete_permission(self, request, obj=None):
        return request.user.is_staff


class UUIDInlineMixin:
    """Mixin that prevents 'None' string from being sent to UUID-backed inline fields."""

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if formfield and isinstance(formfield, forms.UUIDField):
            formfield.__class__ = NoneSafeUUIDField
        return formfield

    def get_formset(self, request, obj=None, **kwargs):
        formset_class = super().get_formset(request, obj, **kwargs)
        original_add_fields = formset_class.add_fields

        def add_fields(self_fs, form, index):
            original_add_fields(self_fs, form, index)
            field = form.fields.get("id")
            if field and isinstance(field, forms.ModelChoiceField):
                field.__class__ = NoneSafeModelChoiceField
            parent_field = form.fields.get(self_fs.fk.name)
            if parent_field and isinstance(parent_field, InlineForeignKeyField):
                parent_field.__class__ = NoneSafeInlineForeignKeyField

        formset_class.add_fields = add_fields
        return formset_class


class ContactEmailInline(StaffPermissionInlineMixin, UUIDInlineMixin, TabularInline):
    """Inline admin for contact email records."""

    model = ContactEmail
    extra = 0
    verbose_name = "Contact Email"
    verbose_name_plural = "Contact Emails"
    fields = ("email_address", "email_type", "verified", "subscribe", "created_at")
    readonly_fields = ("created_at",)

    def get_formset(self, request, obj=None, **kwargs):
        formset_class = super().get_formset(request, obj, **kwargs)
        original_clean = formset_class.clean

        def clean(self_fs):
            original_clean(self_fs)
            primary_count = sum(
                1
                for form in self_fs.forms
                if not form.cleaned_data.get("DELETE", False) and form.cleaned_data.get("email_type") == "primary"
            )
            if primary_count > 1:
                raise ValidationError("A member may only have one primary email.")

        formset_class.clean = clean
        return formset_class


class ContactPhoneInline(StaffPermissionInlineMixin, UUIDInlineMixin, TabularInline):
    """Inline admin for contact phone records."""

    model = ContactPhone
    extra = 0
    verbose_name = "Contact Phone"
    verbose_name_plural = "Contact Phones"
    fields = ("phone_number", "region", "verified", "subscribe", "created_at")
    readonly_fields = ("created_at",)
