"""Helpdesk → Assignment Groups, SLA Targets and Response Templates: how tickets are worked, ServiceNow style.

Group members and managers are chosen among staff who have the Helpdesk app. An SLA target is one row per priority;
it is switched off rather than deleted (both mean "no SLA" for that priority).
"""

from django import forms
from django.contrib import admin
from django.db.models import Count
from unfold.decorators import display

from apps.core.admin import BaseModelAdmin

from ...models import AssignmentGroup, ResponseTemplate, SLATarget, Ticket
from ...services import tickets


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
