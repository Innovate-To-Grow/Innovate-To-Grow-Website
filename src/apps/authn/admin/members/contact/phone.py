import logging

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _

from apps.core.admin import BaseModelAdmin

from ....models import ContactPhone
from .guards import PrivilegedOwnerAdminMixin
from .normalization import (
    apply_phone_changes,
    build_normalization_message,
    compute_phone_changes,
)

logger = logging.getLogger(__name__)


@admin.register(ContactPhone)
class ContactPhoneAdmin(PrivilegedOwnerAdminMixin, BaseModelAdmin):
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
    actions_no_confirmation = ["normalize_all_phones"]

    @admin.display(description="Formatted Number")
    def get_formatted_number(self, obj):
        return obj.get_formatted_number()

    def _report_skipped(self, request, skipped):
        if skipped:
            self.message_user(
                request,
                f"{skipped} phone(s) on staff or superuser accounts skipped — only an I2G Master may change those.",
                level=messages.WARNING,
            )

    @admin.action(description="Mark selected phones as verified")
    def mark_verified(self, request, queryset):
        # ``queryset.update`` bypasses save_model, so re-apply the owner guard: a verified phone on a
        # staff account is an SMS recovery factor for it.
        allowed, skipped = self.manageable(request, queryset)
        updated = allowed.update(verified=True)
        self.message_user(request, f"{updated} phone(s) marked as verified.")
        self._report_skipped(request, skipped)

    @admin.action(description="Mark selected phones as unverified")
    def mark_unverified(self, request, queryset):
        allowed, skipped = self.manageable(request, queryset)
        updated = allowed.update(verified=False)
        self.message_user(request, f"{updated} phone(s) marked as unverified.")
        self._report_skipped(request, skipped)

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
        # ``admin_view`` only enforces is_staff; re-check per-app access so a
        # staff member without the authn app cannot preview member phone PII.
        if not self.has_view_permission(request):
            raise PermissionDenied("You do not have permission to normalize phone numbers.")
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
        # ``admin_view`` only enforces is_staff; re-check per-app access so a
        # staff member without the authn app cannot mutate member phone records.
        if not self.has_change_permission(request):
            raise PermissionDenied("You do not have permission to normalize phone numbers.")
        if request.method != "POST":
            return redirect(reverse("admin:authn_contactphone_normalize_preview"))

        phone_changes, registration_changes = compute_phone_changes()
        try:
            updated_phones, deleted_duplicates, updated_regs = apply_phone_changes(
                phone_changes,
                registration_changes,
            )
        except Exception as exc:  # noqa: BLE001 - report anything, then bail out cleanly
            logger.exception("Failed to apply phone normalization")
            # Include the reason: a swallowed IntegrityError from the unique phone_number index left
            # admins with an unactionable "see logs" message and zero rows fixed.
            messages.error(request, f"Failed to apply phone normalization: {exc}")
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
