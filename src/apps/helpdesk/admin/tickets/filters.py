"""The queue's filters. Two of them have a default instead of "All": the queue opens on people's open tickets.

- Mail: people (default), automated & spam, or everything. Automated mail is hidden unless asked for.
- Status: open statuses (default; "any status" once automated mail is shown), resolved & closed, one status, or any.
- Assignee: me, unassigned, or anyone (default).
- Assignment group: my groups, no group, or one group. SLA: breached, due within 24 hours, or no SLA.
"""

import uuid

from django.contrib import admin
from django.db.models import Q
from django.utils import timezone

from ...models import AssignmentGroup, Ticket
from ...services import sla

Status = Ticket.Status


class _DefaultChoiceFilter(admin.SimpleListFilter):
    """A filter whose "no parameter" state is one of its own choices (shown selected), not "All"."""

    def default_value(self) -> str:
        raise NotImplementedError

    def selected(self) -> str:
        return self.value() or self.default_value()

    def choices(self, changelist):
        current = self.selected()
        for lookup, title in self.lookup_choices:
            yield {
                "selected": current == str(lookup),
                "query_string": changelist.get_query_string({self.parameter_name: lookup}),
                "display": title,
            }


class MailTypeFilter(_DefaultChoiceFilter):
    title = "mail"
    parameter_name = "mail"

    def default_value(self) -> str:
        return "people"

    def lookups(self, request, model_admin):
        return (("people", "People (default)"), ("automated", "Automated & spam"), ("all", "Everything"))

    def queryset(self, request, queryset):
        selected = self.selected()
        if selected == "automated":
            return queryset.filter(Q(automated=True) | Q(status=Status.SPAM))
        if selected == "all":
            return queryset
        return queryset.filter(automated=False).exclude(status=Status.SPAM)


class StatusViewFilter(_DefaultChoiceFilter):
    title = "status"
    parameter_name = "status"

    def __init__(self, request, params, model, model_admin):
        self._mail = request.GET.get(MailTypeFilter.parameter_name, "")
        super().__init__(request, params, model, model_admin)

    def default_value(self) -> str:
        return "any" if self._mail in ("automated", "all") else "open"

    def lookups(self, request, model_admin):
        return (
            ("open", "Open (new, open, pending)"),
            ("closed", "Resolved & closed"),
            *Status.choices,
            ("any", "Any status"),
        )

    def queryset(self, request, queryset):
        selected = self.selected()
        if selected == "open":
            return queryset.filter(status__in=Ticket.OPEN_STATUSES)
        if selected == "closed":
            return queryset.filter(status__in=(Status.RESOLVED, Status.CLOSED))
        if selected in Status.values:
            return queryset.filter(status=selected)
        return queryset


class AssigneeFilter(admin.SimpleListFilter):
    title = "assignee"
    parameter_name = "assignee"

    def lookups(self, request, model_admin):
        return (("me", "Assigned to me"), ("none", "Unassigned"))

    def queryset(self, request, queryset):
        if self.value() == "me":
            return queryset.filter(assignee=request.user)
        if self.value() == "none":
            return queryset.filter(assignee__isnull=True)
        return queryset


class GroupFilter(admin.SimpleListFilter):
    """ServiceNow's "My groups' work": the tickets of every group the signed-in member belongs to, one group, or
    tickets without a group."""

    title = "assignment group"
    parameter_name = "group"

    def lookups(self, request, model_admin):
        groups = [(str(group.pk), group.name) for group in AssignmentGroup.objects.filter(is_active=True)]
        return (("mine", "My groups"), ("none", "No group"), *groups)

    def queryset(self, request, queryset):
        value = self.value()
        if value == "mine":
            # A ticket has one group and a member is in it once, so the join adds no duplicate rows.
            return queryset.filter(assignment_group__members=request.user)
        if value == "none":
            return queryset.filter(assignment_group__isnull=True)
        if value:
            try:
                return queryset.filter(assignment_group_id=uuid.UUID(value))
            except ValueError:
                return queryset.none()
        return queryset


class SLAFilter(admin.SimpleListFilter):
    title = "SLA"
    parameter_name = "sla"

    def lookups(self, request, model_admin):
        return (("breached", "Breached"), ("due_soon", "Due within 24 hours"), ("none", "No SLA"))

    def queryset(self, request, queryset):
        now = timezone.now()
        if self.value() == "breached":
            return queryset.filter(sla.breached_q(now))
        if self.value() == "due_soon":
            return queryset.filter(sla.due_soon_q(now)).exclude(sla.breached_q(now))
        if self.value() == "none":
            return queryset.filter(sla_started_at__isnull=True)
        return queryset


class UnreadFilter(admin.SimpleListFilter):
    title = "unread"
    parameter_name = "unread"

    def lookups(self, request, model_admin):
        return (("yes", "Unread customer message"),)

    def queryset(self, request, queryset):
        return queryset.filter(unread=True) if self.value() == "yes" else queryset
