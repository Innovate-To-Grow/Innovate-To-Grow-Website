from django.core.exceptions import ValidationError
from unfold.admin import TabularInline

from ...models import ContactEmail, ContactPhone


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


class ContactEmailInline(StaffPermissionInlineMixin, TabularInline):
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


class ContactPhoneInline(StaffPermissionInlineMixin, TabularInline):
    """Inline admin for contact phone records."""

    model = ContactPhone
    extra = 0
    verbose_name = "Contact Phone"
    verbose_name_plural = "Contact Phones"
    fields = ("phone_number", "region", "verified", "subscribe", "created_at")
    readonly_fields = ("created_at",)
