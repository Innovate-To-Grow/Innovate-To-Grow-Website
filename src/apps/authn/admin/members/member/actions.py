"""The Member change list's columns and bulk actions."""

from django.contrib import admin

from .helpers import (
    activate_members,
    deactivate_members,
    export_members_response,
    export_members_vcard_response,
    get_full_name_display,
    get_primary_email_display,
    get_primary_phone_display,
)


class MemberAdminActionsMixin:
    @admin.display(description="Primary Email")
    def get_primary_email_display(self, obj):
        return get_primary_email_display(obj)

    @admin.display(description="Primary Phone")
    def get_primary_phone_display(self, obj):
        return get_primary_phone_display(obj)

    @admin.display(description="Full Name")
    def get_full_name_display(self, obj):
        return get_full_name_display(obj)

    @admin.display(description="Account active", boolean=True, ordering="is_active")
    def account_active(self, obj):
        return obj.is_active

    @admin.display(description="Admin", boolean=True, ordering="is_staff")
    def is_admin(self, obj):
        return obj.is_staff

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
