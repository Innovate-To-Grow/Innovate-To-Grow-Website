"""Helpdesk → Categories and Response Templates: how tickets are worked, ServiceNow style (SLA targets are in
``sla_targets``).

Names are unique whatever their case. A template's category is chosen among active ones. A category that tickets
still use is switched off, not deleted (the delete page lists what uses it). Categories are set up here, not from a
ticket's page, so the related-object buttons are not offered. Tickets have no owner (I2G-HELPDESK-01): Assignment
Groups have no admin page any more, and a category's default group is neither shown nor applied (their rows stay).
"""

from django import forms
from django.contrib import admin, messages
from django.db.models import Q

from apps.core.admin import BaseModelAdmin

from ...models import ResponseTemplate, TicketCategory
from ...services.outbound.compose import unknown_placeholders
from .sending import LFTextField

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
    class Meta:
        field_classes = {"body": LFTextField}

    def clean_body(self):
        body = str(self.cleaned_data.get("body") or "")
        unknown = unknown_placeholders(body)
        if unknown:
            raise forms.ValidationError(
                f"Unknown placeholder{'s' if len(unknown) != 1 else ''}: {', '.join(unknown)}. "
                "Use {ticket}, {requester_name}, {subject} or {agent_name}."
            )
        return body


class InUseMixin:
    """A category tickets still use is not deleted (``PROTECT``): its delete page lists what uses it and
    says to switch it off, rather than Django's note that the user may not delete tickets."""

    def get_deleted_objects(self, objs, request):
        deleted, model_count, perms_needed, protected = super().get_deleted_objects(objs, request)
        if protected:
            perms_needed = set()  # nothing would be deleted: it is refused because of what is listed
            messages.warning(
                request,
                "Still in use (listed below), so it cannot be deleted. Switch it off instead (Is active): it stays on "
                "those tickets and is no longer offered.",
            )
        return deleted, model_count, perms_needed, protected


def _active_or(field, current_pk) -> None:
    if field is not None:
        field.queryset = field.queryset.filter(Q(is_active=True) | Q(pk=current_pk))


@admin.register(TicketCategory)
class TicketCategoryAdmin(InUseMixin, BaseModelAdmin):
    require_confirmation = False
    form = UniqueNameForm
    list_display = ("name", "is_active", "order")
    list_editable = ("is_active", "order")
    search_fields = ("name",)
    ordering = ("order", "name")


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
