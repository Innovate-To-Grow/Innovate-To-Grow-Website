from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _
from unfold.decorators import display

from apps.core.admin import BaseModelAdmin

from ....models import ContactPhone
from ..shared.filters import MemberAccountFilter
from ..shared.search import RankedSearchMixin, contact_phone_search_rank
from ..shared.sign_in_warning import SignInWarningAdminMixin, lost_sign_in
from .guards import PrivilegedOwnerAdminMixin
from .normalization_views import PhoneNormalizationViewsMixin
from .phone_verification import ContactPhoneAdminForm, StaffPhoneCodeMixin, same_member, sms_sign_in_status


@admin.register(ContactPhone)
class ContactPhoneAdmin(
    PhoneNormalizationViewsMixin,
    RankedSearchMixin,
    StaffPhoneCodeMixin,
    SignInWarningAdminMixin,
    PrivilegedOwnerAdminMixin,
    BaseModelAdmin,
):
    """Admin for ContactPhone model.

    ``verified`` is never set by hand here: only an SMS code verifies a number (see ``phone_verification``).
    """

    form = ContactPhoneAdminForm
    change_list_template = "admin/authn/contactphone/change_list.html"
    list_display = (
        "phone_number",
        "member",
        "region",
        "get_formatted_number",
        "sms_sign_in",
        "subscribe",
        "created_at",
    )
    list_filter = ("region", "verified", "subscribe", MemberAccountFilter, "created_at")
    search_fields = ("phone_number", "member__first_name", "member__last_name")
    # Numbers are stored as national digits, so a formatted number ("(209) 555-0100", "+1 …") is searched by its
    # digits; the number equal to them comes first (``search.RankedSearchMixin``).
    phone_search_field = "phone_number"
    search_rank = staticmethod(contact_phone_search_rank)
    search_help_text = "Phone number or member name"
    readonly_fields = ("sms_sign_in_status", "created_at", "updated_at")
    list_editable = ("subscribe",)
    autocomplete_fields = ["member"]
    fieldsets = (
        (None, {"fields": ("member", "phone_number", "region")}),
        (_("Status"), {"fields": ("sms_sign_in_status", "verified", "subscribe")}),
        (
            _("Timestamps"),
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )
    actions = ["mark_unverified", "normalize_all_phones"]
    actions_no_confirmation = ["normalize_all_phones"]

    @admin.display(description="Formatted Number")
    def get_formatted_number(self, obj):
        return obj.get_formatted_number()

    @display(description="SMS sign-in", ordering="verified", label={"on": "success", "off": "warning"})
    def sms_sign_in(self, obj):
        return ("on", "Verified") if obj.verified else ("off", "Unverified")

    @admin.display(description="SMS sign-in")
    def sms_sign_in_status(self, obj):
        return sms_sign_in_status(obj)

    def save_model(self, request, obj, form, change):
        # Backstop for ContactPhoneAdminForm's rule, should ``verified`` ever not be a form field: a number moved to
        # another member (or to none) never keeps the verification its previous owner proved.
        if change and obj.verified:
            stored = list(ContactPhone.objects.filter(pk=obj.pk).values_list("member_id", flat=True))
            if stored and not same_member(stored[0], obj.member_id):
                obj.verified = False
        super().save_model(request, obj, form, change)

    def _report_skipped(self, request, skipped):
        if skipped:
            self.message_user(
                request,
                f"{skipped} phone(s) on staff or superuser accounts skipped — only an I2G Master may change those.",
                level=messages.WARNING,
            )

    # There is deliberately no "Mark selected phones as verified": a verified number signs in by SMS, so only a
    # code proves it (the member's account page, or "Verify by SMS code" on the phone's page).
    @admin.action(description="Mark selected phones as unverified (stops SMS sign-in)")
    def mark_unverified(self, request, queryset):
        # ``queryset.update`` bypasses save_model, so re-apply the owner guard.
        allowed, skipped = self.manageable(request, queryset)
        with lost_sign_in(request, set(allowed.values_list("member_id", flat=True))):
            updated = allowed.update(verified=False)
        self.message_user(request, f"{updated} phone(s) marked as unverified.")
        self._report_skipped(request, skipped)
