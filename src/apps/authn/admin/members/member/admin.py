"""
Member admin configuration.
"""

import uuid

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from unfold.forms import AdminPasswordChangeForm

from apps.core.admin import BaseModelAdmin

from ....models import Member
from ..inlines.contacts import ContactEmailInline, ContactPhoneInline
from ..primary_switch.switch import PrimarySwitchAdminMixin
from ..shared.filters import MEMBER_FILTERS, AccountTypeFilter
from ..shared.search import RankedSearchMixin, member_search_rank
from ..shared.sign_in_warning import lost_sign_in, member_page_row
from .actions import MemberAdminActionsMixin
from .forms import MemberChangeForm, MemberCreationForm
from .helpers import normalize_inline_uuid_none_values
from .lockout import OWN_ACCOUNT_NOTE, MemberAdminLockoutMixin
from .views import MemberAdminViewsMixin


@admin.register(Member)
class MemberAdmin(
    MemberAdminActionsMixin,
    MemberAdminViewsMixin,
    MemberAdminLockoutMixin,
    PrimarySwitchAdminMixin,
    RankedSearchMixin,
    BaseModelAdmin,
    UserAdmin,
):
    """Custom admin for Member with profile, contact, import, and export tooling.

    **Account active** (``is_active``) is the account's own flag; each email address and phone has its own Verified
    (a way to sign in) and Subscribed (newsletters). The filters and labels keep the two apart (``filters``,
    ``help_texts``), and a save that leaves the member no verified email or phone is warned about, not refused
    (``sign_in_warning``). The primary email is switched on its own page (``primary_switch``).
    """

    # URL names whose views only render list rows, and so never need the multi-megabyte
    # base64 ``profile_image`` (or the password hash) that a bare SELECT would pull for every row.
    list_shaped_url_names = frozenset({"authn_member_changelist", "autocomplete"})

    def get_queryset(self, request):
        qs = super().get_queryset(request).prefetch_related("contact_emails", "contact_phones")
        match = getattr(request, "resolver_match", None)
        if match is not None and match.url_name in self.list_shaped_url_names:
            qs = qs.defer("profile_image", "password")
        return qs

    form = MemberChangeForm
    add_form = MemberCreationForm
    # Django's default AdminPasswordChangeForm does not apply Unfold INPUT_CLASSES;
    # password fields render with no visible borders on the themed admin page.
    change_password_form = AdminPasswordChangeForm
    change_form_template = "admin/authn/member/change_form.html"
    list_display = (
        "get_full_name_display",
        "get_primary_email_display",
        "get_primary_phone_display",
        "organization",
        "account_active",
        "is_admin",
        "date_joined",
    )
    list_filter = (*MEMBER_FILTERS, AccountTypeFilter, "date_joined")
    search_fields = (
        "contact_emails__email_address",
        "first_name",
        "middle_name",
        "last_name",
        "id",
        "organization",
        "title",
    )
    # Every email address, names, organization, title and Member UUID, plus a phone number typed on its own; the
    # exact address comes first, here and in every member picker (``search.RankedSearchMixin``).
    phone_search_field = "contact_phones__phone_number"
    search_rank = staticmethod(member_search_rank)
    search_help_text = "Email, name, phone, organization or UUID"
    ordering = ("-date_joined",)
    readonly_fields = ("member_uuid", "registration_pending", "date_joined", "last_login")
    fieldsets = (
        (_("Member Info"), {"fields": ("member_uuid",)}),
        (_("Account"), {"fields": ("is_active", "registration_pending")}),
        (None, {"fields": ("password",)}),
        (
            _("Personal Info"),
            {"fields": ("first_name", "middle_name", "last_name", "organization", "title", "profile_image")},
        ),
        (_("Admin access"), {"fields": ("is_staff",)}),
        (_("Important Dates"), {"fields": ("last_login", "date_joined"), "classes": ("collapse",)}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("password1", "password2")}),
        (_("Personal Info"), {"fields": ("first_name", "middle_name", "last_name", "organization", "title")}),
        (_("Member Status"), {"fields": ("is_active",)}),
    )
    inlines = [ContactEmailInline, ContactPhoneInline]
    change_list_template = "admin/authn/member/change_list.html"
    actions = [
        "activate_members",
        "deactivate_members",
        "export_members_to_excel",
        "export_members_to_vcard",
        "sync_all_members_to_sheet",
    ]
    actions_no_confirmation = ["export_members_to_excel", "export_members_to_vcard", "sync_all_members_to_sheet"]
    # Explicit allowlist for the generic "Export selected data" action. Without it the default is
    # every concrete column, which for Member meant offering (and previewing on screen) the base64
    # profile image, the password hash, ``is_superuser`` (a mirror of ``is_staff``) and the vestigial AbstractUser
    # ``email``. Mirrors the curated columns in services/members/export/excel.py.
    export_fields = (
        "id",
        "first_name",
        "middle_name",
        "last_name",
        "organization",
        "title",
        "is_active",
        "date_joined",
    )

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        # Only surface the impersonate button when the request may actually use it and the target is not an Admin
        # account — mirrors the rule enforced in ``impersonate_view``.
        target = self.get_object(request, object_id)
        extra_context["show_impersonate"] = bool(
            self.has_change_permission(request, target) and target is not None and not target.is_staff
        )
        if self.is_own_account(request, target):
            extra_context["own_account_note"] = OWN_ACCOUNT_NOTE
        return super().change_view(request, object_id, form_url=form_url, extra_context=extra_context)

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        normalize_inline_uuid_none_values(request)
        return super().changeform_view(request, object_id=object_id, form_url=form_url, extra_context=extra_context)

    def save_form(self, request, form, change):
        obj = super().save_form(request, form, change)
        self._ensure_new_member_uuid(obj, change)
        return obj

    def save_model(self, request, obj, form, change):
        self._ensure_new_member_uuid(obj, change)
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        # Unticking Verified (or removing a row) on the last verified email or phone is allowed, with a warning.
        with lost_sign_in(request, [form.instance.pk] if change else []):
            super().save_related(request, form, formsets, change)

    def get_confirmation_diff(self, request, obj, form, formsets, action_type):
        diff = super().get_confirmation_diff(request, obj, form, formsets, action_type)
        warning = member_page_row(obj, formsets) if action_type == "change" and diff else None
        return [*diff, warning] if warning else diff

    @staticmethod
    def _ensure_new_member_uuid(obj, change):
        if not change and getattr(obj, "id", None) in (None, "", "None"):
            obj.id = uuid.uuid4()
