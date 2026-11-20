"""Helpdesk → Assignment Groups, Categories and Response Templates: how tickets are worked, ServiceNow style (SLA
targets are in ``sla_targets``).

Names are unique whatever their case. Group members and managers are chosen among staff who have the Helpdesk app;
someone who lost it stays listed (marked) until removed by hand, so an unrelated save never drops them. A category's
default group and a template's category are chosen among active ones. A group or category that tickets still use is
switched off, not deleted (the delete page lists what uses it). Groups, categories and members are set up here, not
from a ticket's page, so the related-object buttons are not offered.
"""

from django import forms
from django.contrib import admin
from django.db.models import Count, Q
from unfold.decorators import display

from apps.core.admin import BaseModelAdmin

from ...models import AssignmentGroup, ResponseTemplate, TicketCategory
from ...services import tickets
from ...services.outbound.compose import unknown_placeholders

RELATED_FLAGS = ("can_add_related", "can_change_related", "can_delete_related", "can_view_related")


def no_related_buttons(form, *names) -> None:
    for name in names:
        widget = getattr(form.base_fields.get(name), "widget", None)
        for flag in RELATED_FLAGS:
            if hasattr(widget, flag):
                setattr(widget, flag, False)


class UniqueNameForm(forms.ModelForm):
    """A name taken in another case ("events" beside "Events") is refused; spaces are tidied."""

    def clean_name(self):
        name = " ".join(str(self.cleaned_data.get("name") or "").split())
        model = self._meta.model
        if model.objects.filter(name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(f"“{name}” is taken already (names are compared whatever their case).")
        return name


class ResponseTemplateForm(UniqueNameForm):
    def clean_body(self):
        body = str(self.cleaned_data.get("body") or "").replace("\r\n", "\n")
        unknown = unknown_placeholders(body)
        if unknown:
            raise forms.ValidationError(
                f"Unknown placeholder{'s' if len(unknown) != 1 else ''}: {', '.join(unknown)}. "
                "Use {ticket}, {requester_name}, {subject} or {agent_name}."
            )
        return body


def _active_or(field, current_pk) -> None:
    if field is not None:
        field.queryset = field.queryset.filter(Q(is_active=True) | Q(pk=current_pk))


@admin.register(AssignmentGroup)
class AssignmentGroupAdmin(BaseModelAdmin):
    require_confirmation = False
    form = UniqueNameForm
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

    def get_form(self, request, obj=None, change=False, **kwargs):
        from apps.authn.models import Member

        form = super().get_form(request, obj, change, **kwargs)
        staff = {member.pk for member in tickets.helpdesk_staff()}
        kept = set()
        if obj is not None:
            kept = set(obj.members.values_list("pk", flat=True)) | ({obj.manager_id} if obj.manager_id else set())
        people = Member.objects.filter(pk__in=staff | kept).order_by("first_name", "last_name")
        for name in ("members", "manager"):
            field = form.base_fields.get(name)
            if field is not None:
                field.queryset = people
                field.label_from_instance = lambda member: (
                    str(member) if member.pk in staff else f"{member} (no Helpdesk access)"
                )
        no_related_buttons(form, "manager", "members")
        return form


@admin.register(TicketCategory)
class TicketCategoryAdmin(BaseModelAdmin):
    require_confirmation = False
    form = UniqueNameForm
    list_display = ("name", "default_group", "is_active", "order")
    list_editable = ("is_active", "order")
    list_select_related = ("default_group",)
    search_fields = ("name",)
    ordering = ("order", "name")

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        _active_or(form.base_fields.get("default_group"), obj.default_group_id if obj is not None else None)
        no_related_buttons(form, "default_group")
        return form


@admin.register(ResponseTemplate)
class ResponseTemplateAdmin(BaseModelAdmin):
    require_confirmation = False
    form = ResponseTemplateForm
    list_display = ("name", "category", "is_active", "order")
    list_editable = ("is_active", "order")
    list_filter = ("is_active", "category")
    list_select_related = ("category",)
    search_fields = ("name", "body")
    ordering = ("order", "name")

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        _active_or(form.base_fields.get("category"), obj.category_id if obj is not None else None)
        no_related_buttons(form, "category")
        return form
