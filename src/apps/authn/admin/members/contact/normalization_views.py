"""Normalize ALL phone numbers: the change-list action, its preview page and the apply step, limited to rows the admin may manage."""

import logging

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import path, reverse

from ....models import ContactPhone
from .normalization import (
    apply_phone_changes,
    build_normalization_message,
    compute_phone_changes,
)

logger = logging.getLogger("apps.authn.admin.members.contact.phone")  # its log name before the split


class PhoneNormalizationViewsMixin:
    def _drop_unmanageable_phone_changes(self, request, phone_changes):
        """Remove changes targeting rows owned by members the requester may not manage.

        ``apply_phone_changes`` rewrites and deletes rows across *all* owners, so the per-app
        change grant checked in the view is not enough on its own — apply the same owner guard the
        bulk actions get via ``manageable``, and report what was skipped.
        """
        owners = {
            str(phone.pk): phone.member
            for phone in ContactPhone.objects.select_related("member").filter(
                pk__in=[change["pk"] for change in phone_changes]
            )
        }
        allowed = []
        skipped = 0
        for change in phone_changes:
            if not self._can_manage(request, owners.get(change["pk"])):
                skipped += 1
                continue
            allowed.append(change)
        self._report_skipped(request, skipped)
        return allowed

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
        if not request.user.is_superuser:
            phone_changes = self._drop_unmanageable_phone_changes(request, phone_changes)
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
