"""List filters for Members, Contact Emails and Contact Phones that keep the account flag apart from the address flags.

- **Account active** (``Member.is_active``) belongs to the account: signing in, and the All subscribers, All active
  members and Staff audiences. No contact flag changes it, and it changes no contact.
- **Verified** belongs to each address or phone: it can be used to sign in. Unverified addresses still get mail.
- **Subscribed** belongs to each address: the All subscribers audience (newsletters).

Every condition is an ``EXISTS`` on the member's own rows, so filtering never duplicates a member.
"""

from django.contrib import admin
from django.db.models import Exists, OuterRef, Q

from ...models import ContactEmail, ContactPhone


def _emails(**conditions):
    return Exists(ContactEmail.objects.filter(member=OuterRef("pk"), **conditions))


def _phones(**conditions):
    return Exists(ContactPhone.objects.filter(member=OuterRef("pk"), **conditions))


class ChoiceFilter(admin.SimpleListFilter):
    """A list filter whose choices are ``(value, label, condition)`` from ``options()``."""

    def options(self):  # pragma: no cover - every filter below overrides it
        return ()

    def lookups(self, request, model_admin):
        return [(value, label) for value, label, _condition in self.options()]

    def queryset(self, request, queryset):
        for value, _label, condition in self.options():
            if self.value() == value:
                return queryset.filter(condition)
        return queryset


# --- Members ----------------------------------------------------------------------------------------------------------


class AccountActiveFilter(ChoiceFilter):
    title = "Account active"
    parameter_name = "account"

    def options(self):
        return (
            ("active", "Yes", Q(is_active=True)),
            ("inactive", "No", Q(is_active=False)),
            ("pending", "Unfinished sign-up", Q(registration_pending=True)),
        )


class PrimaryEmailFilter(ChoiceFilter):
    title = "Primary email"
    parameter_name = "primary_email"

    def options(self):
        return (
            ("verified", "Verified", _emails(email_type="primary", verified=True)),
            ("unverified", "Unverified", _emails(email_type="primary", verified=False)),
            ("none", "No primary email", ~_emails(email_type="primary")),
        )


class UnverifiedEmailFilter(ChoiceFilter):
    title = "Unverified emails"
    parameter_name = "unverified_email"

    def options(self):
        return (
            ("yes", "Has an unverified email", _emails(verified=False)),
            ("no", "No unverified email", ~_emails(verified=False)),
        )


class NewsletterFilter(ChoiceFilter):
    title = "Newsletter (All subscribers)"
    parameter_name = "newsletter"

    def options(self):
        subscribed_primary = _emails(email_type="primary", subscribe=True)
        return (
            ("primary", "Subscribed at the primary", subscribed_primary),
            ("other_only", "Subscribed at another address only", ~subscribed_primary & _emails(subscribe=True)),
            ("none", "Not subscribed at any address", ~_emails(subscribe=True)),
        )


class PhoneFilter(ChoiceFilter):
    title = "Phone"
    parameter_name = "phone"

    def options(self):
        return (
            ("verified", "Verified (SMS sign-in)", _phones(verified=True)),
            ("unverified", "Unverified only", _phones() & ~_phones(verified=True)),
            ("none", "No phone", ~_phones()),
        )


MEMBER_FILTERS = (AccountActiveFilter, PrimaryEmailFilter, UnverifiedEmailFilter, NewsletterFilter, PhoneFilter)


# --- Contact Emails and Contact Phones --------------------------------------------------------------------------------


class EmailVerifiedFilter(ChoiceFilter):
    title = "Verified (sign-in)"
    parameter_name = "verified_status"

    def options(self):
        return (
            # Just the address flag: an unlinked address or an inactive account's address does not sign anyone in.
            ("verified", "Verified", Q(verified=True)),
            ("unverified", "Unverified emails", Q(verified=False)),
            (
                "unverified_primary",
                "Unverified primary emails",
                Q(verified=False, email_type="primary", member__isnull=False),
            ),
        )


class EmailSubscribedFilter(ChoiceFilter):
    title = "Subscribed (newsletters)"
    parameter_name = "subscribed"

    def options(self):
        return (
            ("yes", "Subscribed", Q(subscribe=True)),
            ("no", "Unsubscribed", Q(subscribe=False)),
        )


class MemberAccountFilter(ChoiceFilter):
    """The owner's account, for a contact row (an unlinked row has none)."""

    title = "Member account"
    parameter_name = "account"

    def options(self):
        return (
            ("active", "Account active", Q(member__is_active=True)),
            ("inactive", "Account inactive", Q(member__is_active=False)),
            ("staff", "Staff or I2G Master", Q(member__is_staff=True) | Q(member__is_superuser=True)),
            ("unlinked", "No member (unlinked)", Q(member__isnull=True)),
        )
