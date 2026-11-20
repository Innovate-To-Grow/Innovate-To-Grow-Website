"""Helpdesk → SLA Targets: one row per priority, in order of severity, with the first-response and resolution times.

Targets are policy (ServiceNow keeps SLA definitions to its administrators): Helpdesk staff see them, only an I2G
Master changes them, so a desk cannot loosen its own targets. A target is switched off rather than deleted (a missing
row and an inactive one both mean "no SLA" for new tickets of that priority), and a priority's row is created only
when it has none (the migration creates all four).
"""

from django import forms
from django.contrib import admin
from unfold.decorators import display

from apps.core.admin import BaseModelAdmin

from ...models import SLATarget, Ticket
from ...services.sla.priority import PRIORITY_RANK

MINUTES_HELP = "In minutes (60 = 1 hour, 1440 = 1 day); calendar time, not business hours."


def _is_master(request) -> bool:
    return bool(getattr(request.user, "is_superuser", False))


def _duration(minutes: int) -> str:
    days, rest = divmod(int(minutes or 0), 24 * 60)
    hours, mins = divmod(rest, 60)
    parts = [f"{days} d" if days else "", f"{hours} h" if hours else "", f"{mins} min" if mins else ""]
    return " ".join(part for part in parts if part) or "0 min"


@admin.register(SLATarget)
class SLATargetAdmin(BaseModelAdmin):
    require_confirmation = False
    list_display = ("priority_label", "response_display", "resolution_display", "is_active")
    list_editable = ("is_active",)

    def get_ordering(self, request):
        return [PRIORITY_RANK.asc()]

    def get_fields(self, request, obj=None):
        first = "priority_label" if obj is not None else "priority"
        return (first, "response_minutes", "resolution_minutes", "is_active")

    def get_readonly_fields(self, request, obj=None):
        return ("priority_label",) if obj is not None else ()

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "priority":
            taken = set(SLATarget.objects.values_list("priority", flat=True))
            choices = [choice for choice in Ticket.Priority.choices if choice[0] not in taken]
            return forms.ChoiceField(choices=choices, label="Priority")
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name in ("response_minutes", "resolution_minutes") and field is not None:
            field.help_text = f"{db_field.help_text} {MINUTES_HELP}"
        return field

    @display(description="Priority", ordering=PRIORITY_RANK)
    def priority_label(self, obj):
        return dict(Ticket.Priority.choices).get(obj.priority, obj.priority)

    @display(description="First response within")
    def response_display(self, obj):
        return _duration(obj.response_minutes)

    @display(description="Resolution within")
    def resolution_display(self, obj):
        return _duration(obj.resolution_minutes)

    def has_add_permission(self, request):
        missing = set(Ticket.Priority.values) - set(SLATarget.objects.values_list("priority", flat=True))
        return bool(missing) and _is_master(request) and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return _is_master(request) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False  # switch a target off instead: a missing row and an inactive one both mean "no SLA"
