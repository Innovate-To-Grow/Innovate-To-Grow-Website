"""
Member admin configuration.
"""

import logging
import re
import uuid

from django.conf import settings
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import redirect
from django.urls import path
from django.utils.http import unquote
from django.utils.translation import gettext_lazy as _
from unfold.forms import AdminPasswordChangeForm

from apps.core.admin import BaseModelAdmin
from apps.core.utils.access import user_can_manage_member

from ...models import ImpersonationToken, Member
from ...services.members.profile_image import ALLOWED_CONTENT_TYPES, ProfileImageError, split_data_uri
from .forms import MemberChangeForm, MemberCreationForm
from .helpers import (
    activate_members,
    deactivate_members,
    download_template_view,
    export_excel_view,
    export_members_response,
    export_members_vcard_response,
    get_full_name_display,
    get_primary_email_display,
    get_primary_phone_display,
    import_excel_view,
    normalize_inline_uuid_none_values,
)
from .inlines import ContactEmailInline, ContactPhoneInline

logger = logging.getLogger(__name__)


@admin.register(Member)
class MemberAdmin(BaseModelAdmin, UserAdmin):
    """Custom admin for Member with profile, contact, import, and export tooling."""

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
        "is_active",
        "is_staff",
        "date_joined",
    )
    list_filter = ("is_active", "is_staff", "date_joined")
    search_fields = (
        "contact_emails__email_address",
        "first_name",
        "middle_name",
        "last_name",
        "id",
        "organization",
        "title",
    )
    ordering = ("-date_joined",)
    readonly_fields = ("member_uuid", "date_joined", "last_login")
    fieldsets = (
        (_("Member Info"), {"fields": ("member_uuid",)}),
        (None, {"fields": ("password",)}),
        (
            _("Personal Info"),
            {"fields": ("first_name", "middle_name", "last_name", "organization", "title", "profile_image")},
        ),
        (
            _("Permissions"),
            {
                "fields": ("is_active", "is_staff", "admin_apps"),
                "classes": ("collapse",),
            },
        ),
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
    # profile image, ``is_superuser``, the ``admin_apps`` grant list and the vestigial AbstractUser
    # ``email``. Mirrors the curated columns in services/members/export_excel.py.
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

    @admin.display(description="Primary Email")
    def get_primary_email_display(self, obj):
        return get_primary_email_display(obj)

    @admin.display(description="Primary Phone")
    def get_primary_phone_display(self, obj):
        return get_primary_phone_display(obj)

    @admin.display(description="Full Name")
    def get_full_name_display(self, obj):
        return get_full_name_display(obj)

    @admin.action(description="Activate selected members")
    def activate_members(self, request, queryset):
        activate_members(self, request, queryset)

    @admin.action(description="Deactivate selected members")
    def deactivate_members(self, request, queryset):
        deactivate_members(self, request, queryset)

    @admin.action(description="Export selected members to Excel")
    def export_members_to_excel(self, request, queryset):
        return export_members_response(queryset)

    @admin.action(description="Export selected members as vCard (.vcf)")
    def export_members_to_vcard(self, request, queryset):
        return export_members_vcard_response(queryset)

    @admin.action(description="Sync ALL members to Google Sheet")
    def sync_all_members_to_sheet(self, request, queryset):
        try:
            from apps.authn.services.members.sheet_sync import sync_members_to_sheet

            rows = sync_members_to_sheet(sync_type="full")
            self.message_user(request, f"Synced {rows} members to Google Sheet.")
        except Exception as exc:
            self.message_user(request, f"Sheet sync failed: {exc}", level="error")

    def get_urls(self):
        custom_urls = [
            path("import-excel/", self.admin_site.admin_view(self.import_excel_view), name="authn_member_import_excel"),
            path(
                "import-template/",
                self.admin_site.admin_view(self.download_template_view),
                name="authn_member_import_template",
            ),
            path("export-excel/", self.admin_site.admin_view(self.export_excel_view), name="authn_member_export_excel"),
            path(
                "<path:object_id>/impersonate/",
                self.admin_site.admin_view(self.impersonate_view),
                name="authn_member_impersonate",
            ),
            path(
                "<path:object_id>/profile-image/",
                self.admin_site.admin_view(self.profile_image_view),
                name="authn_member_profile_image",
            ),
        ]
        return custom_urls + super().get_urls()

    def profile_image_view(self, request, object_id):
        """Stream a member's stored profile image so the change form never inlines it.

        ``profile_image`` holds a base64 ``data:`` URI in a TextField; rendering it inside an
        ``<img src>`` made the change page grow with the image and truncate mid-form. Like every other
        custom admin URL here, ``admin_site.admin_view`` only enforces ``is_staff``, so re-check
        per-app access.
        """
        if not self.has_view_permission(request):
            raise PermissionDenied("You do not have permission to view members.")
        member = self.get_object(request, unquote(str(object_id)))
        if member is None or not member.profile_image:
            raise Http404("This member has no profile image.")
        try:
            raw, mime = split_data_uri(member.profile_image)
        except ProfileImageError as exc:
            raise Http404("Stored profile image could not be decoded.") from exc

        response = HttpResponse(raw, content_type=mime)
        if mime not in ALLOWED_CONTENT_TYPES:
            # Legacy rows could hold any client-supplied type; never let one render inline.
            response["Content-Type"] = "application/octet-stream"
            response["Content-Disposition"] = f'attachment; filename="profile-{member.pk}"'
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    def impersonate_view(self, request, object_id):
        # ``admin_site.admin_view`` only enforces is_staff, so this custom URL must
        # re-check authorization itself (Django never runs the per-app model
        # permissions for a standalone admin view). Require authn-app access, and
        # never let a non-superuser account be impersonated into a privileged one:
        # impersonation is an end-user support tool, and minting a token for a
        # staff/superuser account would be a privilege-escalation vector.
        if not self.has_change_permission(request):
            raise PermissionDenied("You do not have permission to impersonate members.")
        # POST-only: minting a token is a state change, and on GET Django performs no CSRF check,
        # so a cross-site navigation could make an admin issue (and burn) impersonation credentials.
        if request.method != "POST":
            raise PermissionDenied("Impersonation must be started with a POST request.")
        # ``self.get_object`` swallows the ValidationError a non-UUID <path:object_id> would raise;
        # ``get_object_or_404`` only translates DoesNotExist and so returned a 500 instead of a 404.
        member = self.get_object(request, unquote(str(object_id)))
        if member is None:
            raise Http404("No member matches the given query.")
        if member.is_staff or member.is_superuser:
            raise PermissionDenied("Staff and superuser accounts cannot be impersonated.")
        token = ImpersonationToken.generate_token()
        ImpersonationToken.objects.create(token=token, member=member, created_by=request.user)
        logger.info("Administrator %s began impersonating member %s", request.user.id, member.id)
        frontend_url = (getattr(settings, "FRONTEND_URL", "") or "").strip().rstrip("/")
        return redirect(f"{frontend_url}/impersonate-login#token={token}")

    # Granting admin-app access or staff status is an I2G Master (superuser)
    # responsibility. A non-superuser admin must not be able to widen their own
    # (or anyone's) privileges by editing these fields, so they are read-only for
    # non-superusers — Django drops any submitted value for read-only fields, so
    # this is enforced server-side, not just hidden in the rendered form.
    superuser_only_fields = ("is_staff", "admin_apps")

    @staticmethod
    def can_manage_target(request, target) -> bool:
        """Whether ``request.user`` may act on the privileged parts of ``target``'s account."""
        return user_can_manage_member(request.user, target)

    def user_change_password(self, request, id, form_url=""):  # noqa: A002 - UserAdmin's signature
        """Refuse password resets on privileged accounts unless the actor is a superuser.

        ``UserAdmin``'s inherited ``<id>/password/`` route is gated only by ``has_change_permission``,
        which here is the object-independent authn-app predicate — so any staffer with that grant could
        set the superuser's password and log in as them, defeating ``superuser_only_fields``.
        """
        target = self.get_object(request, unquote(str(id)))
        if not self.can_manage_target(request, target):
            raise PermissionDenied("Only an I2G Master may change a privileged account's password.")
        return super().user_change_password(request, id, form_url=form_url)

    def has_delete_permission(self, request, obj=None):
        # Deleting a privileged account is itself a privileged operation — same scope as
        # ``protected_target_fields``. The object-level check covers the delete view (and hides its
        # button); the bulk path is backstopped in ``delete_queryset`` below.
        if obj is not None and not self.can_manage_target(request, obj):
            return False
        return super().has_delete_permission(request, obj)

    def delete_queryset(self, request, queryset):
        # ``delete_selected`` is gated only by the object-independent ``has_delete_permission``,
        # so re-apply the per-object guard before anything is removed.
        for member in queryset:
            if not self.can_manage_target(request, member):
                raise PermissionDenied("Only an I2G Master may delete a staff or superuser account.")
        return super().delete_queryset(request, queryset)

    # Editable on an ordinary member, but not on a staff/superuser account unless the actor is an
    # I2G Master — deactivating or renaming a privileged account is itself a privileged operation.
    protected_target_fields = ("is_active",)

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if not request.user.is_superuser:
            for field in self.superuser_only_fields:
                if field not in readonly:
                    readonly.append(field)
            if obj is not None and not self.can_manage_target(request, obj):
                for field in self.protected_target_fields:
                    if field not in readonly:
                        readonly.append(field)
        return readonly

    def get_search_results(self, request, queryset, search_term):
        """Extend the default search (email/name/id/...) with phone-number matching.

        Phones are stored as national digits via ``ContactPhone.phone_number``, so the
        query is reduced to digits and an 11-digit ``1XXXXXXXXXX`` is also tried as the
        national ``XXXXXXXXXX`` — letting ``+1 555 123 4567``, ``15551234567``,
        ``5551234567``, and partials like ``555123`` / ``1234567`` all find the same
        member. Phone matches are taken from the same base queryset so list filters
        still apply, and ``may_have_duplicates`` makes the changelist de-duplicate
        members that own several matching phones.
        """
        base = queryset
        queryset, may_have_duplicates = super().get_search_results(request, base, search_term)

        digits = re.sub(r"\D", "", search_term or "")
        if digits:
            national = digits[1:] if len(digits) == 11 and digits.startswith("1") else digits
            phone_q = Q(contact_phones__phone_number__icontains=national)
            if national != digits:
                phone_q |= Q(contact_phones__phone_number__icontains=digits)
            queryset |= base.filter(phone_q)
            may_have_duplicates = True

        return queryset, may_have_duplicates

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        # Only surface the impersonate button when the request may actually use it
        # (authn-app access) and the target is a non-privileged account — mirrors
        # the authorization enforced in ``impersonate_view``.
        target = self.get_object(request, object_id)
        extra_context["show_impersonate"] = bool(
            self.has_change_permission(request, target)
            and target is not None
            and not (target.is_staff or target.is_superuser)
        )
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

    @staticmethod
    def _ensure_new_member_uuid(obj, change):
        if not change and getattr(obj, "id", None) in (None, "", "None"):
            obj.id = uuid.uuid4()

    def import_excel_view(self, request):
        return import_excel_view(self, request)

    def download_template_view(self, request):
        return download_template_view(self, request)

    def export_excel_view(self, request):
        return export_excel_view(self, request)
