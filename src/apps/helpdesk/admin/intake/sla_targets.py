"""Helpdesk → SLA Targets: one row per priority, in order of severity, with the first-response and resolution times.

Every Admin sees and changes them. A target is switched off rather than deleted (a missing
row and an inactive one both mean "no SLA" for new tickets of that priority), and a priority's row is created only
when it has none (the migration creates all four). A change applies to new tickets and to priority changes, not to
clocks already running.
"""

from django import forms
from django.contrib import admin
from unfold.decorators import display

from apps.core.admin import BaseModelAdmin

from ...models import SLATarget, Ticket
from ...services.sla.priority import PRIORITY_RANK

MINUTES_HELP = (
    "In minutes (60 = 1 hour, 1440 = 1 day); calendar time, not business hours. A change applies to new tickets and to "
    "priority changes, not to clocks already running."
)


def _duration(minutes: int) -> str:
    days, rest = divmod(int(minutes or 0), 24 * 60)
    hours, mins = divmod(rest, 60)
    parts = [f"{days} d" if days else "", f"{hours} h" if hours else "", f"{mins} min" if mins else ""]
    return " ".join(part for part in parts if part) or "0 min"


def _missing() -> set:
    return set(Ticket.Priority.values) - set(SLATarget.objects.values_list("priority", flat=True))


@admin.register(SLATarget)
class SLATargetAdmin(BaseModelAdmin):
    require_confirmation = False
    list_display = ("priority_label", "response_display", "resolution_display", "is_active")
    list_editable = ("is_active",)

    def get_ordering(self, request):
        return [PRIORITY_RANK.asc()]

    def get_list_display(self, request):
        return [name for name in super().get_list_display(request) if name != "created_at"]

    def get_fieldsets(self, request, obj=None):
        first = "priority_label" if obj is not None else "priority"
        return ((None, {"fields": (first, "response_minutes", "resolution_minutes", "is_active")}),)

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

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        if add:
            # The last missing priority leaves nothing to add after it.
            context["show_save_and_add_another"] = len(_missing()) > 1
        return super().render_change_form(request, context, add=add, change=change, form_url=form_url, obj=obj)

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
        return bool(_missing()) and super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False  # switch a target off instead: a missing row and an inactive one both mean "no SLA"
