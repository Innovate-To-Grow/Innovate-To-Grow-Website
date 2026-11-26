"""Normalize ALL phone numbers: the change-list action, its preview page and the apply step."""

import logging

from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.urls import path, reverse

from .normalization import (
    apply_phone_changes,
    build_normalization_message,
    compute_phone_changes,
)

logger = logging.getLogger("apps.authn.admin.members.contact.phone")  # its log name before the split


class PhoneNormalizationViewsMixin:
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
        return custom + self.verify_by_code_urls() + super().get_urls()

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
