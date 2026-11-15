"""The queue's filters. Two of them have a default instead of "All": the queue opens on people's open tickets.

- Mail: people (default), automated & spam, or everything. Automated mail is hidden unless asked for.
- Status: open statuses (default; "any status" once automated mail is shown), resolved & closed, one status, or any.
- Assignee: me, unassigned, or anyone (default).
"""

from django.contrib import admin
from django.db.models import Q

from ..models import Ticket

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


class UnreadFilter(admin.SimpleListFilter):
    title = "unread"
    parameter_name = "unread"

    def lookups(self, request, model_admin):
        return (("yes", "Unread customer message"),)

    def queryset(self, request, queryset):
        return queryset.filter(unread=True) if self.value() == "yes" else queryset
