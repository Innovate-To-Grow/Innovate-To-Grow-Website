"""
Member admin configuration.
"""

import logging

from django.conf import settings
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.shortcuts import get_object_or_404, redirect
from django.urls import path
from django.utils.translation import gettext_lazy as _
from unfold.forms import AdminPasswordChangeForm

from core.admin import BaseModelAdmin

from ...models import ImpersonationToken, Member
from .forms import MemberChangeForm, MemberCreationForm
from .inlines import ContactEmailInline, ContactPhoneInline
from .member_helpers import (
    activate_members,
    deactivate_members,
    download_template_view,
    export_excel_view,
    export_members_response,
    get_full_name_display,
    get_primary_email_display,
    import_excel_view,
)

logger = logging.getLogger(__name__)


@admin.register(Member)
class MemberAdmin(BaseModelAdmin, UserAdmin):
    """Custom admin for Member with profile, contact, import, and export tooling."""

    form = MemberChangeForm
    add_form = MemberCreationForm
    # Django's default AdminPasswordChangeForm does not apply Unfold INPUT_CLASSES;
    # password fields render with no visible borders on the themed admin page.
    change_password_form = AdminPasswordChangeForm
    change_form_template = "admin/authn/member/change_form.html"
    list_display = (
        "get_full_name_display",
        "get_primary_email_display",
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
    filter_horizontal = ("user_permissions",)
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
                "fields": ("is_active", "is_staff", "user_permissions"),
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
    actions = ["activate_members", "deactivate_members", "export_members_to_excel"]

    @admin.display(description="Primary Email")
    def get_primary_email_display(self, obj):
        return get_primary_email_display(obj)

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
        ]
        return custom_urls + super().get_urls()

    def impersonate_view(self, request, object_id):
        member = get_object_or_404(Member, pk=object_id)
        token = ImpersonationToken.generate_token()
        ImpersonationToken.objects.create(token=token, member=member, created_by=request.user)
        logger.info("Admin %s created impersonation token for member %s", request.user.id, member.id)
        frontend_url = (getattr(settings, "FRONTEND_URL", "") or "").strip().rstrip("/")
        return redirect(f"{frontend_url}/impersonate-login?token={token}")

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["show_impersonate"] = True
        return super().change_view(request, object_id, form_url=form_url, extra_context=extra_context)

    def import_excel_view(self, request):
        return import_excel_view(self, request)

    def download_template_view(self, request):
        return download_template_view(self, request)

    def export_excel_view(self, request):
        return export_excel_view(self, request)
