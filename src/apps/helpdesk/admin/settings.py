"""Helpdesk → Settings (one row of admin-editable limits, retention periods and switches) and → Categories.

Shadow mode is shown, never editable: this release has no sending code. Saving the settings wakes the ingest, so mail
that waited while the helpdesk was off is imported.
"""

from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse

from apps.core.admin import BaseModelAdmin

from ..models import HelpdeskSettings, TicketCategory
from ..services.ingest import jobs


@admin.register(HelpdeskSettings)
class HelpdeskSettingsAdmin(BaseModelAdmin):
    readonly_fields = ("shadow_mode",)
    fieldsets = (
        ("Switches", {"fields": ("enabled", "shadow_mode", "pause_while_campaign_sending")}),
        (
            "Import",
            {
                "fields": (
                    "ingest_batch_size",
                    "ingest_max_seconds",
                    "max_attempts",
                    "message_max_bytes",
                    "attachment_max_bytes",
                    "body_text_max_chars",
                    "body_html_max_chars",
                    "blocked_extensions",
                    "warn_extensions",
                )
            },
        ),
        (
            "Tickets",
            {
                "fields": (
                    "reopen_window_days",
                    "flood_threshold",
                    "flood_window_minutes",
                    "spam_scl_threshold",
                    "backfill_age_hours",
                )
            },
        ),
        (
            "Retention",
            {
                "fields": (
                    "automated_retention_days",
                    "spam_retention_days",
                    "closed_body_retention_days",
                    "attachment_retention_days",
                    "ticket_retention_days",
                )
            },
        ),
    )

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not HelpdeskSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        """One row: the list goes straight to it (or to the add form while the defaults are not saved yet)."""
        current = HelpdeskSettings.objects.first()
        if current is not None:
            return HttpResponseRedirect(reverse("admin:helpdesk_helpdesksettings_change", args=[current.pk]))
        if self.has_add_permission(request):
            return HttpResponseRedirect(reverse("admin:helpdesk_helpdesksettings_add"))
        return super().changelist_view(request, extra_context)

    def save_model(self, request, obj, form, change):
        obj.shadow_mode = True
        super().save_model(request, obj, form, change)
        if obj.enabled:
            jobs.ensure_scheduled()


@admin.register(TicketCategory)
class TicketCategoryAdmin(BaseModelAdmin):
    require_confirmation = False
    list_display = ("name", "is_active", "order")
    list_editable = ("is_active", "order")
    search_fields = ("name",)
    ordering = ("order", "name")
