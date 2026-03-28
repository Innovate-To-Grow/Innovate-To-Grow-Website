from unfold.admin import StackedInline, TabularInline

from ...models import ContactEmail, ContactPhone, MemberProfile
from .forms import MemberProfileInlineForm


class MemberProfileInline(StackedInline):
    """Inline admin for MemberProfile displayed inside the member editor."""

    model = MemberProfile
    form = MemberProfileInlineForm
    can_delete = False
    verbose_name = "Profile"
    verbose_name_plural = "Profile"
    extra = 0
    max_num = 1
    fields = ("profile_image", "updated_at")
    readonly_fields = ("updated_at",)


class ContactEmailInline(TabularInline):
    """Inline admin for contact email records."""

    model = ContactEmail
    extra = 0
    verbose_name = "Contact Email"
    verbose_name_plural = "Contact Emails"
    fields = ("email_address", "email_type", "verified", "subscribe", "created_at")
    readonly_fields = ("created_at",)


class ContactPhoneInline(TabularInline):
    """Inline admin for contact phone records."""

    model = ContactPhone
    extra = 0
    verbose_name = "Contact Phone"
    verbose_name_plural = "Contact Phones"
    fields = ("phone_number", "region", "verified", "subscribe", "created_at")
    readonly_fields = ("created_at",)
