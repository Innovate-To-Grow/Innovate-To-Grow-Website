"""
Contact information admin configuration.
Includes ContactEmail and ContactPhone.
"""

import logging

from django.contrib import admin, messages
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _

from core.admin import BaseModelAdmin

from ...models import ContactEmail, ContactPhone
from ...models.contact.phone_regions import PHONE_REGION_CHOICES
from ...services.contacts.contact_phones import infer_region_from_e164, normalize_to_national

logger = logging.getLogger(__name__)

# ============================================================================
# Contact Email Admin
# ============================================================================


@admin.register(ContactEmail)
class ContactEmailAdmin(BaseModelAdmin):
    """Admin for ContactEmail model."""

    list_display = ("email_address", "member", "email_type", "verified", "subscribe", "created_at")
    list_filter = ("email_type", "verified", "subscribe", "created_at")
    search_fields = ("email_address", "member__first_name", "member__last_name")
    readonly_fields = ("created_at", "updated_at")
    list_editable = ("verified", "subscribe")
    autocomplete_fields = ["member"]

    fieldsets = (
        (None, {"fields": ("member", "email_address", "email_type")}),
        (_("Status"), {"fields": ("verified", "subscribe")}),
        (_("Timestamps"), {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    # Actions
    actions = ["mark_verified", "mark_unverified", "toggle_subscribe"]

    @admin.action(description="Mark selected emails as verified")
    def mark_verified(self, request, queryset):
        updated = queryset.update(verified=True)
        self.message_user(request, f"{updated} email(s) marked as verified.")

    @admin.action(description="Mark selected emails as unverified")
    def mark_unverified(self, request, queryset):
        updated = queryset.update(verified=False)
        self.message_user(request, f"{updated} email(s) marked as unverified.")

    @admin.action(description="Toggle subscription status")
    def toggle_subscribe(self, request, queryset):
        for email in queryset:
            email.subscribe = not email.subscribe
            email.save()
        self.message_user(request, f"Toggled subscription for {queryset.count()} email(s).")


# ============================================================================
# Contact Phone Admin
# ============================================================================


@admin.register(ContactPhone)
class ContactPhoneAdmin(BaseModelAdmin):
    """Admin for ContactPhone model."""

    change_list_template = "admin/authn/contactphone/change_list.html"
    list_display = ("phone_number", "member", "region", "get_formatted_number", "verified", "subscribe", "created_at")
    list_filter = ("region", "verified", "subscribe", "created_at")
    search_fields = ("phone_number", "member__first_name", "member__last_name")
    readonly_fields = ("created_at", "updated_at")
    list_editable = ("verified", "subscribe")
    autocomplete_fields = ["member"]

    fieldsets = (
        (None, {"fields": ("member", "phone_number", "region")}),
        (_("Status"), {"fields": ("verified", "subscribe")}),
        (_("Timestamps"), {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
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

    # ------------------------------------------------------------------
    # Custom URLs for the normalize preview / apply flow
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Shared helper: compute proposed changes
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_phone_changes():
        """Return (phone_changes, reg_changes) without writing anything."""
        region_dict = dict(PHONE_REGION_CHOICES)
        phone_changes = []
        seen_normalized: dict[str, dict] = {}

        for cp in ContactPhone.objects.select_related("member").order_by("created_at"):
            new_region = infer_region_from_e164(cp.phone_number, cp.region)
            new_number = normalize_to_national(cp.phone_number, new_region)

            number_changed = new_number != cp.phone_number
            region_changed = new_region != cp.region

            is_duplicate = False
            duplicate_of = None
            dedup_key = f"{new_region}:{new_number}"
            if dedup_key in seen_normalized:
                is_duplicate = True
                duplicate_of = seen_normalized[dedup_key]
            else:
                seen_normalized[dedup_key] = {
                    "pk": str(cp.pk),
                    "member": str(cp.member) if cp.member else "-",
                }

            phone_changes.append(
                {
                    "pk": str(cp.pk),
                    "member": str(cp.member) if cp.member else "-",
                    "old_number": cp.phone_number,
                    "new_number": new_number,
                    "old_region": cp.region,
                    "old_region_display": region_dict.get(cp.region, cp.region),
                    "new_region": new_region,
                    "new_region_display": region_dict.get(new_region, new_region),
                    "number_changed": number_changed,
                    "region_changed": region_changed,
                    "is_duplicate": is_duplicate,
                    "duplicate_of": duplicate_of,
                    "changed": number_changed or region_changed,
                }
            )

        # EventRegistration phone cleanup — strip formatting only (E.164 stays for this model)
        import re

        from event.models import EventRegistration

        reg_changes = []
        for reg in EventRegistration.objects.exclude(attendee_phone="").only(
            "pk",
            "attendee_phone",
            "attendee_first_name",
            "attendee_last_name",
            "ticket_code",
        ):
            digits = re.sub(r"\D", "", reg.attendee_phone.strip())
            new_phone = f"+{digits}" if digits else ""
            if new_phone != reg.attendee_phone:
                reg_changes.append(
                    {
                        "pk": str(reg.pk),
                        "ticket_code": reg.ticket_code,
                        "attendee": f"{reg.attendee_first_name} {reg.attendee_last_name}".strip() or "-",
                        "old_phone": reg.attendee_phone,
                        "new_phone": new_phone,
                    }
                )

        return phone_changes, reg_changes

    # ------------------------------------------------------------------
    # Preview view (GET) – read-only
    # ------------------------------------------------------------------

    def _normalize_preview_view(self, request):
        phone_changes, reg_changes = self._compute_phone_changes()

        changed_phones = [c for c in phone_changes if c["changed"] or c["is_duplicate"]]
        duplicate_count = sum(1 for c in phone_changes if c["is_duplicate"])

        context = {
            **self.admin_site.each_context(request),
            "title": "Normalize Phone Numbers — Preview",
            "phone_changes": changed_phones,
            "reg_changes": reg_changes,
            "total_phones": len(phone_changes),
            "phones_to_fix": len([c for c in phone_changes if c["changed"]]),
            "duplicate_count": duplicate_count,
            "regs_to_fix": len(reg_changes),
            "apply_url": reverse("admin:authn_contactphone_normalize_apply"),
            "cancel_url": reverse("admin:authn_contactphone_changelist"),
        }
        return render(request, "admin/authn/contactphone/normalize_preview.html", context)

    # ------------------------------------------------------------------
    # Apply view (POST) – writes to DB
    # ------------------------------------------------------------------

    def _normalize_apply_view(self, request):
        if request.method != "POST":
            return redirect(reverse("admin:authn_contactphone_normalize_preview"))

        phone_changes, reg_changes = self._compute_phone_changes()

        updated_phones = 0
        deleted_duplicates = 0
        updated_regs = 0

        try:
            with transaction.atomic():
                seen: dict[str, str] = {}

                for change in phone_changes:
                    pk = change["pk"]
                    new_number = change["new_number"]

                    if change["is_duplicate"]:
                        ContactPhone.objects.filter(pk=pk).delete()
                        deleted_duplicates += 1
                        continue

                    seen[new_number] = pk

                    if change["changed"]:
                        ContactPhone.objects.filter(pk=pk).update(
                            phone_number=new_number,
                            region=change["new_region"],
                        )
                        updated_phones += 1

                from event.models import EventRegistration

                for rc in reg_changes:
                    EventRegistration.objects.filter(pk=rc["pk"]).update(
                        attendee_phone=rc["new_phone"],
                    )
                    updated_regs += 1

        except Exception:
            logger.exception("Failed to apply phone normalization")
            messages.error(request, "Failed to apply phone normalization. See logs for details.")
            return redirect(reverse("admin:authn_contactphone_normalize_preview"))

        parts = []
        if updated_phones:
            parts.append(f"{updated_phones} phone(s) normalized")
        if deleted_duplicates:
            parts.append(f"{deleted_duplicates} duplicate(s) removed")
        if updated_regs:
            parts.append(f"{updated_regs} event registration phone(s) cleaned")
        if not parts:
            parts.append("No changes needed")

        messages.success(request, ". ".join(parts) + ".")
        return redirect(reverse("admin:authn_contactphone_changelist"))
