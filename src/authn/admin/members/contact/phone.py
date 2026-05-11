import logging

from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _

from core.admin import BaseModelAdmin

from ....models import ContactPhone
from .normalization import (
    apply_phone_changes,
    build_normalization_message,
    compute_phone_changes,
)

logger = logging.getLogger(__name__)


@admin.register(ContactPhone)
class ContactPhoneAdmin(BaseModelAdmin):
    """Admin for ContactPhone model."""

    change_list_template = "admin/authn/contactphone/change_list.html"
    list_display = (
        "phone_number",
        "member",
        "region",
        "get_formatted_number",
        "verified",
        "subscribe",
        "created_at",
    )
    list_filter = ("region", "verified", "subscribe", "created_at")
    search_fields = ("phone_number", "member__first_name", "member__last_name")
    readonly_fields = ("created_at", "updated_at")
    list_editable = ("verified", "subscribe")
    autocomplete_fields = ["member"]
    fieldsets = (
        (None, {"fields": ("member", "phone_number", "region")}),
        (_("Status"), {"fields": ("verified", "subscribe")}),
        (
            _("Timestamps"),
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )
    actions = ["mark_verified", "mark_unverified", "normalize_all_phones"]

    @admin.display(description="Formatted Number")
    def get_formatted_number(self, obj):
        return obj.get_formatted_number()

    @admin.action(description="Mark selected phones as verified")
    def mark_verified(self, request, queryset):
        updated = queryset.update(verified=True)
        self.message_user(request, f"{updated} phone(s) marked as verified.")

    @admin.action(description="Mark selected phones as unverified")
    def mark_unverified(self, request, queryset):
        updated = queryset.update(verified=False)
        self.message_user(request, f"{updated} phone(s) marked as unverified.")

    @admin.action(description="Normalize ALL phone numbers (preview first)")
    def normalize_all_phones(self, request, queryset):
        return redirect(reverse("admin:authn_contactphone_normalize_preview"))

    def get_urls(self):
        custom = [
            path(
                "normalize-phones-preview/",
                self.admin_site.admin_view(self._normalize_preview_view),
                name="authn_contactphone_normalize_preview",
            ),
            path(
                "normalize-phones-apply/",
                self.admin_site.admin_view(self._normalize_apply_view),
                name="authn_contactphone_normalize_apply",
            ),
        ]
        return custom + super().get_urls()

    def _normalize_preview_view(self, request):
        phone_changes, registration_changes = compute_phone_changes()
        changed_phones = [change for change in phone_changes if change["changed"] or change["is_duplicate"]]
        context = {
            **self.admin_site.each_context(request),
            "title": "Normalize Phone Numbers - Preview",
            "phone_changes": changed_phones,
            "reg_changes": registration_changes,
            "total_phones": len(phone_changes),
            "phones_to_fix": len([c for c in phone_changes if c["changed"]]),
            "duplicate_count": sum(1 for c in phone_changes if c["is_duplicate"]),
            "regs_to_fix": len(registration_changes),
            "apply_url": reverse("admin:authn_contactphone_normalize_apply"),
            "cancel_url": reverse("admin:authn_contactphone_changelist"),
        }
        return render(request, "admin/authn/contactphone/normalize_preview.html", context)

    def _normalize_apply_view(self, request):
        if request.method != "POST":
            return redirect(reverse("admin:authn_contactphone_normalize_preview"))

        phone_changes, registration_changes = compute_phone_changes()
        try:
            updated_phones, deleted_duplicates, updated_regs = apply_phone_changes(
                phone_changes,
                registration_changes,
            )
        except Exception:
            logger.exception("Failed to apply phone normalization")
            messages.error(
                request,
                "Failed to apply phone normalization. See logs for details.",
            )
            return redirect(reverse("admin:authn_contactphone_normalize_preview"))

        messages.success(
            request,
            build_normalization_message(
                updated_phones,
                deleted_duplicates,
                updated_regs,
            ),
        )
        return redirect(reverse("admin:authn_contactphone_changelist"))
