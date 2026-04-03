from unfold.admin import TabularInline

from ...models import ContactEmail, ContactPhone


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
