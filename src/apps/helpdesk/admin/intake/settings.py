"""Helpdesk → Settings: one row of admin-editable limits, retention periods and switches (Categories and Response
templates are in ``service_desk``, SLA targets in ``sla_targets``).

Shadow mode is a switch here: on (the default), nothing is sent; off, staff reply from the ticket page and the
acknowledgement is sent when switched on (their labels and the acknowledgement text's checks are in ``sending``).
Staff get no helpdesk email (I2G-HELPDESK-01): they work tickets in the admin. Every Admin changes them. Every change is in the admin history and the log. Above the form sits the intake card (its controls are in ``intake``).
Saving the settings switched on restarts the intake and wakes the ingest, so mail that arrived while the helpdesk was
off is read and imported.
"""

import logging

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.urls import path, reverse

from apps.core.admin import BaseModelAdmin

from ...models import HelpdeskSettings
from ...services.ingest.pipeline import jobs
from ...services.intake import jobs as intake_jobs
from ...services.intake import status as intake_status
from . import controls as intake
from .sending import SendingFieldsMixin

logger = logging.getLogger(__name__)


@admin.register(HelpdeskSettings)
class HelpdeskSettingsAdmin(SendingFieldsMixin, BaseModelAdmin):
    # The intake card (its own POST forms) sits above the settings form, outside it.
    change_form_outer_before_template = "admin/helpdesk/intake/card.html"
    fieldsets = (
        ("Switches", {"fields": ("enabled", "shadow_mode", "pause_while_campaign_sending")}),
        (
            "Sending",
            {
                "description": "Used only while shadow mode is off.",
                "fields": ("send_acknowledgement", "acknowledgement_text"),
            },
        ),
        ("SLA and automation", {"fields": ("sla_warning_percent", "auto_close_resolved_days")}),
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
                    "bulk_bcl_threshold",
                    "reply_match_window_days",
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

    class Media:
        css = {"all": ("helpdesk/css/helpdesk.css",)}

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not HelpdeskSettings.objects.exists()

    def get_urls(self):
        control = path("intake/", self.admin_site.admin_view(intake.intake_view), name="helpdesk_intake")
        return [control, *super().get_urls()]

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        context["helpdesk_intake"] = intake_status.card()
        return super().render_change_form(request, context, add=add, change=change, form_url=form_url, obj=obj)

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        """One row: the list goes straight to it (or to the add form while the defaults are not saved yet)."""
        if not self.has_view_or_change_permission(request):
            raise PermissionDenied
        current = HelpdeskSettings.objects.first()
        if current is not None:
            return HttpResponseRedirect(reverse("admin:helpdesk_helpdesksettings_change", args=[current.pk]))
        if self.has_add_permission(request):
            return HttpResponseRedirect(reverse("admin:helpdesk_helpdesksettings_add"))
        return super().changelist_view(request, extra_context)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if "shadow_mode" in form.changed_data:
            state = "on (nothing is sent)" if obj.shadow_mode else "off (replies and notifications can be sent)"
            logger.info("helpdesk_shadow_mode changed=%s by=%s", obj.shadow_mode, getattr(request.user, "pk", ""))
            messages.warning(request, f"Shadow mode is now {state}.")
        if obj.enabled:
            jobs.ensure_scheduled()
            intake_jobs.ensure_scheduled()
