"""Helpdesk → Settings (one row of admin-editable limits, retention periods and switches) and → Categories
(assignment groups, SLA targets and response templates are in ``service_desk``).

Shadow mode is a switch here: on (the default), nothing is sent; off, staff reply from the ticket page and the
acknowledgement and assignment notifications are sent when switched on. Only an I2G Master (superuser) can change
these sending switches and the acknowledgement's text; every change is in the admin history and the log. Above the form sits the intake card (its controls are in ``intake``). Saving the
settings switched on restarts the intake and wakes the ingest, so mail that arrived while the helpdesk was off is read
and imported.
"""

import logging

from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import path, reverse

from apps.core.admin import BaseModelAdmin

from ...models import HelpdeskSettings, TicketCategory
from ...services.ingest.pipeline import jobs
from ...services.intake import jobs as intake_jobs
from ...services.intake import status as intake_status
from . import controls as intake

logger = logging.getLogger(__name__)


@admin.register(HelpdeskSettings)
class HelpdeskSettingsAdmin(BaseModelAdmin):
    # The intake card (its own POST forms) sits above the settings form, outside it.
    change_form_outer_before_template = "admin/helpdesk/intake/card.html"
    fieldsets = (
        ("Switches", {"fields": ("enabled", "shadow_mode", "pause_while_campaign_sending")}),
        (
            "Sending and notifications",
            {
                "description": "Used only while shadow mode is off.",
                "fields": ("send_acknowledgement", "acknowledgement_text", "notify_assignment"),
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

    # What makes the helpdesk send mail from the site's address, and what its automatic email says: an I2G Master's
    # decision, not every Helpdesk grant holder's (a compromised helpdesk account must not turn it into a mailer).
    SENDING_FIELDS = ("shadow_mode", "send_acknowledgement", "acknowledgement_text", "notify_assignment")

    def get_readonly_fields(self, request, obj=None):
        fields = tuple(super().get_readonly_fields(request, obj))
        if getattr(request.user, "is_superuser", False):
            return fields
        return (*fields, *self.SENDING_FIELDS)

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


@admin.register(TicketCategory)
class TicketCategoryAdmin(BaseModelAdmin):
    require_confirmation = False
    list_display = ("name", "default_group", "is_active", "order")
    list_editable = ("is_active", "order")
    list_select_related = ("default_group",)
    search_fields = ("name",)
    ordering = ("order", "name")
