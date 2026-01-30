"""
Member and MemberProfile admin configuration.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _

from mobileid.models import Barcode, MobileID

from ..models import (
    I2GMemberGroup,
    Member,
    MemberContactInfo,
    MemberProfile,
)
from .forms import MemberImportForm

# ============================================================================
# Inline Admin Classes
# ============================================================================


class MemberProfileInline(admin.StackedInline):
    """Inline admin for MemberProfile - displayed within Member admin."""

    model = MemberProfile
    can_delete = False
    verbose_name = "Profile"
    verbose_name_plural = "Profile"
    extra = 0
    fields = ("display_name", "profile_image", "updated_at")
    readonly_fields = ("updated_at",)


class MemberContactInfoInline(admin.TabularInline):
    """Inline admin for MemberContactInfo - displayed within Member admin."""

    model = MemberContactInfo
    extra = 0
    verbose_name = "Contact Info"
    verbose_name_plural = "Contact Infos"
    autocomplete_fields = ["contact_email", "contact_phone"]
    readonly_fields = ("created_at", "updated_at")


class BarcodeInline(admin.TabularInline):
    """Inline admin for Barcode - displayed within Member admin."""

    model = Barcode
    fk_name = "model_user"
    extra = 0
    verbose_name = "Barcode"
    verbose_name_plural = "Barcodes"
    fields = ("barcode_type", "barcode", "profile_name", "created_at")
    readonly_fields = ("created_at",)


class MobileIDInline(admin.TabularInline):
    """Inline admin for MobileID - displayed within Member admin."""

    model = MobileID
    fk_name = "model_user"
    extra = 0
    verbose_name = "Mobile ID"
    verbose_name_plural = "Mobile IDs"
    autocomplete_fields = ["user_barcode"]


# ============================================================================
# Member Admin (Custom User Admin)
# ============================================================================


@admin.register(Member)
class MemberAdmin(UserAdmin):
    """
    Custom admin for Member model.
    Extends Django's UserAdmin with additional fields specific to Member.
    """

    # List display columns
    list_display = (
        "username",
        "email",
        "get_full_name_display",
        "organization",
        "is_active",
        "is_active_member",
        "is_staff",
        "date_joined",
        "get_groups_display",
    )

    # List filters
    list_filter = (
        "is_active",
        "is_active_member",
        "is_staff",
        "is_superuser",
        "groups",
        "date_joined",
    )

    # Search fields
    search_fields = (
        "username",
        "email",
        "first_name",
        "middle_name",
        "last_name",
        "member_uuid",
        "organization",
    )

    # Ordering
    ordering = ("-date_joined",)

    # Read-only fields
    readonly_fields = ("member_uuid", "date_joined", "last_login")

    # Filter horizontal for groups and permissions
    filter_horizontal = ("groups", "user_permissions")

    # Fieldsets - organized sections in the edit form
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (
            _("Personal Info"),
            {"fields": ("first_name", "middle_name", "last_name", "email", "contect_email", "organization")},
        ),
        (
            _("Member Info"),
            {"fields": ("member_uuid", "is_active_member"), "description": "Member-specific information"},
        ),
        (
            _("Permissions"),
            {
                "fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions"),
                "classes": ("collapse",),
            },
        ),
        (
            _("Important Dates"),
            {
                "fields": ("last_login", "date_joined"),
                "classes": ("collapse",),
            },
        ),
    )

    # Fieldsets for adding a new user
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "email", "password1", "password2"),
            },
        ),
        (
            _("Personal Info"),
            {
                "fields": ("first_name", "middle_name", "last_name", "organization"),
            },
        ),
        (
            _("Member Status"),
            {
                "fields": ("is_active_member",),
            },
        ),
    )

    # Inline models
    inlines = [MemberProfileInline, MemberContactInfoInline, BarcodeInline, MobileIDInline]

    # Enable change list template customization
    change_list_template = "admin/authn/member/change_list.html"

    # Custom display methods
    @admin.display(description="Full Name")
    def get_full_name_display(self, obj):
        return obj.get_full_name() or "-"

    @admin.display(description="Groups")
    def get_groups_display(self, obj):
        groups = obj.groups.all()
        if groups:
            return ", ".join([g.name for g in groups[:3]])
        return "-"

    # Actions
    actions = ["activate_members", "deactivate_members", "assign_default_groups"]

    @admin.action(description="Activate selected members")
    def activate_members(self, request, queryset):
        updated = queryset.update(is_active_member=True, is_active=True)
        self.message_user(request, f"{updated} member(s) activated.")

    @admin.action(description="Deactivate selected members")
    def deactivate_members(self, request, queryset):
        updated = queryset.update(is_active_member=False)
        self.message_user(request, f"{updated} member(s) deactivated.")

    @admin.action(description="Create default I2G groups")
    def assign_default_groups(self, request, queryset):
        I2GMemberGroup.create_default_groups()
        self.message_user(request, "Default I2G groups created successfully.")

    # =========================================================================
    # Custom URLs for Excel Import
    # =========================================================================

    def get_urls(self):
        """Add custom URLs for import functionality."""
        urls = super().get_urls()
        custom_urls = [
            path(
                "import-excel/",
                self.admin_site.admin_view(self.import_excel_view),
                name="authn_member_import_excel",
            ),
            path(
                "import-template/",
                self.admin_site.admin_view(self.download_template_view),
                name="authn_member_import_template",
            ),
        ]
        return custom_urls + urls

    def import_excel_view(self, request):
        """Handle Excel file import."""
        from ..services.import_members import import_members_from_excel

        context = {
            **self.admin_site.each_context(request),
            "title": "Import Members",
            "opts": self.model._meta,
            "form": MemberImportForm(),
            "result": None,
        }

        if request.method == "POST":
            form = MemberImportForm(request.POST, request.FILES)
            context["form"] = form

            if form.is_valid():
                excel_file = form.cleaned_data["excel_file"]
                default_password = form.cleaned_data.get("set_password") or None

                result = import_members_from_excel(
                    file=excel_file,
                    default_password=default_password,
                    update_existing=False,
                )

                context["result"] = result

                if result.success:
                    self.message_user(
                        request,
                        f"Import complete: {result.created_count} created, "
                        f"{result.skipped_count} skipped"
                        + (f", {len(result.errors)} error(s)" if result.errors else ""),
                        level="success" if not result.errors else "warning",
                    )

        return render(request, "admin/authn/member/import_excel.html", context)

    def download_template_view(self, request):
        """Download Excel template for member import."""
        from ..services.import_members import generate_template_excel

        try:
            content = generate_template_excel()
            response = HttpResponse(
                content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            response["Content-Disposition"] = 'attachment; filename="member_import_template.xlsx"'
            return response
        except ImportError as e:
            self.message_user(request, str(e), level="error")
            return HttpResponseRedirect(reverse("admin:authn_member_changelist"))


# ============================================================================
# Member Profile Admin
# ============================================================================


@admin.register(MemberProfile)
class MemberProfileAdmin(admin.ModelAdmin):
    """Admin for MemberProfile model."""

    list_display = ("model_user", "display_name", "has_profile_image_display", "updated_at")
    list_filter = ("updated_at",)
    search_fields = ("model_user__username", "model_user__email", "display_name")
    readonly_fields = ("updated_at",)
    autocomplete_fields = ["model_user"]

    fieldsets = (
        (None, {"fields": ("model_user",)}),
        (_("Profile Information"), {"fields": ("display_name", "profile_image")}),
        (_("Timestamps"), {"fields": ("updated_at",), "classes": ("collapse",)}),
    )

    @admin.display(description="Has Image", boolean=True)
    def has_profile_image_display(self, obj):
        return obj.has_profile_image()
