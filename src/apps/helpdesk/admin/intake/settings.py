"""Helpdesk → Settings (one row of admin-editable limits, retention periods and switches) and → Categories.

Shadow mode is a switch here: on (the default), nothing is sent; off, staff reply from the ticket page and the
acknowledgement and assignment notifications are sent when switched on. Every change of it is in the admin history
(the change message names it). Above the form sits the intake card (its controls are in ``intake``). Saving the
settings switched on restarts the intake and wakes the ingest, so mail that arrived while the helpdesk was off is read
and imported.
"""

import logging

from django.contrib import admin, messages
from django.db.models import Count
from django.http import HttpResponseRedirect
from django.urls import path, reverse
from unfold.decorators import display

from apps.core.admin import BaseModelAdmin

from ...models import AssignmentGroup, HelpdeskSettings, ResponseTemplate, SLATarget, Ticket, TicketCategory
from ...services import tickets
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


@admin.register(AssignmentGroup)
class AssignmentGroupAdmin(BaseModelAdmin):
    require_confirmation = False
    list_display = ("name", "description", "manager", "member_count", "is_active", "order")
    list_editable = ("is_active", "order")
    list_select_related = ("manager",)
    search_fields = ("name", "description")
    filter_horizontal = ("members",)
    ordering = ("order", "name")

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(member_total=Count("members", distinct=True))

    @display(description="Members", ordering="member_total")
    def member_count(self, obj):
        return getattr(obj, "member_total", 0)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "members":
            kwargs["queryset"] = _staff_queryset()
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "manager":
            kwargs["queryset"] = _staff_queryset()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


def _staff_queryset():
    from apps.authn.models import Member

    return Member.objects.filter(pk__in=[member.pk for member in tickets.helpdesk_staff()])


@admin.register(SLATarget)
class SLATargetAdmin(BaseModelAdmin):
    require_confirmation = False
    list_display = ("priority_label", "response_display", "resolution_display", "is_active")
    list_editable = ("is_active",)
    fields = ("priority", "response_minutes", "resolution_minutes", "is_active")

    def get_readonly_fields(self, request, obj=None):
        return ("priority",) if obj is not None else ()

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "priority":
            from django import forms

            return forms.ChoiceField(choices=Ticket.Priority.choices, label="Priority")
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    @display(description="Priority", ordering="priority")
    def priority_label(self, obj):
        return dict(Ticket.Priority.choices).get(obj.priority, obj.priority)

    @display(description="First response within")
    def response_display(self, obj):
        return _duration(obj.response_minutes)

    @display(description="Resolution within")
    def resolution_display(self, obj):
        return _duration(obj.resolution_minutes)

    def has_delete_permission(self, request, obj=None):
        return False  # switch a target off instead: a missing row and an inactive one both mean "no SLA"


def _duration(minutes: int) -> str:
    days, rest = divmod(int(minutes or 0), 24 * 60)
    hours, mins = divmod(rest, 60)
    parts = [f"{days} d" if days else "", f"{hours} h" if hours else "", f"{mins} min" if mins else ""]
    return " ".join(part for part in parts if part) or "0 min"


@admin.register(ResponseTemplate)
class ResponseTemplateAdmin(BaseModelAdmin):
    require_confirmation = False
    list_display = ("name", "category", "is_active", "order")
    list_editable = ("is_active", "order")
    list_filter = ("is_active", "category")
    list_select_related = ("category",)
    search_fields = ("name", "body")
    ordering = ("order", "name")
