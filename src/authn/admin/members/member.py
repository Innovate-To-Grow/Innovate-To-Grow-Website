"""
Member admin configuration.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.urls import path
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin as UnfoldModelAdmin

from ...models import Member
from .forms import MemberChangeForm, MemberCreationForm
from .inlines import ContactEmailInline, ContactPhoneInline, MemberProfileInline
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


@admin.register(Member)
class MemberAdmin(UnfoldModelAdmin, UserAdmin):
    """Custom admin for Member with profile, contact, import, and export tooling."""

    form = MemberChangeForm
    add_form = MemberCreationForm
    list_display = (
        "get_primary_email_display",
        "get_full_name_display",
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
    )
    ordering = ("-date_joined",)
    readonly_fields = ("member_uuid", "date_joined", "last_login")
    filter_horizontal = ("user_permissions",)
    fieldsets = (
        (None, {"fields": ("password",)}),
        (_("Personal Info"), {"fields": ("first_name", "middle_name", "last_name", "organization")}),
        (
            _("Member Info"),
            {"fields": ("member_uuid",), "description": "Member-specific information"},
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
        (_("Personal Info"), {"fields": ("first_name", "middle_name", "last_name", "organization")}),
        (_("Member Status"), {"fields": ("is_active",)}),
    )
    inlines = [MemberProfileInline, ContactEmailInline, ContactPhoneInline]
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
        ]
        return custom_urls + super().get_urls()

    def import_excel_view(self, request):
        return import_excel_view(self, request)

    def download_template_view(self, request):
        return download_template_view(self, request)

    def export_excel_view(self, request):
        return export_excel_view(self, request)
