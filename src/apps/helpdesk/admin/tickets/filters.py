"""The queue's filters. Two of them have a default instead of "All": the queue opens on people's open tickets.

- Mail: people (default), automated & spam, or everything. Automated mail is hidden unless asked for.
- Status: open statuses (default; "any status" once automated mail is shown), resolved & closed, one status, or any.
  The two groups have keys of their own ("active", "done"), so "open" and "closed" mean the single statuses.
- Reply: awaiting a staff reply (``outbound.activity.awaiting_reply``), or any (default). The sidebar's Helpdesk badge
  counts the same tickets (``awaiting_reply_badge``).
- SLA: breached, at risk (a running clock past the settings' warning share of its target), or no SLA.

Tickets have no owner (I2G-HELPDESK-01), so there is no assignee or group filter; an old bookmark that still names
one is redirected without it (``TicketAdmin.changelist_view``).
"""

import logging

from django.contrib import admin
from django.db.models import Q
from django.utils import timezone

from apps.core.utils.access import user_is_admin

from ...models import HelpdeskSettings, Ticket
from ...services import sla
from ...services.outbound import activity
from ...services.sla.priority import SEVERITY

Status = Ticket.Status
logger = logging.getLogger(__name__)
ACTIVE, DONE = "active", "done"


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
        return "any" if self._mail in ("automated", "all") else ACTIVE

    def lookups(self, request, model_admin):
        return (
            (ACTIVE, "Open (new, in progress, on hold)"),
            (DONE, "Resolved & closed"),
            # Spam is never among people's mail (Mail: people, the default).
            *(choice for choice in Status.choices if choice[0] != Status.SPAM or self._mail in ("automated", "all")),
            ("any", "Any status"),
        )

    def queryset(self, request, queryset):
        selected = self.selected()
        if selected == ACTIVE:
            return queryset.filter(status__in=Ticket.OPEN_STATUSES)
        if selected == DONE:
            return queryset.filter(status__in=(Status.RESOLVED, Status.CLOSED))
        if selected in Status.values:
            return queryset.filter(status=selected)
        return queryset


class ReplyFilter(admin.SimpleListFilter):
    """The tickets whose next move is a staff reply: the sidebar's "Awaiting Reply" and its badge."""

    title = "reply"
    parameter_name = "reply"

    def lookups(self, request, model_admin):
        return (("awaiting", "Awaiting a staff reply"),)

    def queryset(self, request, queryset):
        return activity.awaiting_reply(queryset) if self.value() == "awaiting" else queryset


def awaiting_reply_badge(request) -> str:
    """The sidebar badge of Helpdesk: the tickets ``ReplyFilter`` lists, the same count for every Admin ("" when there
    is none, or for anyone else; "99+" above 99). One query, shared for ``activity.AWAITING_CACHE_SECONDS``."""
    if not user_is_admin(getattr(request, "user", None)):
        return ""
    try:
        total = activity.awaiting_reply_count()
    except Exception:
        logger.exception("Could not count the helpdesk tickets awaiting a reply.")
        return ""
    if total <= 0:
        return ""
    return "99+" if total > 99 else str(total)


class SLAFilter(admin.SimpleListFilter):
    title = "SLA"
    parameter_name = "sla"

    def lookups(self, request, model_admin):
        share = int(HelpdeskSettings.load().sla_warning_percent)
        return (("breached", "Breached"), ("at_risk", f"At risk (past {share}% of the target)"), ("none", "No SLA"))

    def queryset(self, request, queryset):
        now = timezone.now()
        if self.value() == "breached":
            return queryset.filter(sla.breached_q(now))
        if self.value() == "at_risk":
            share = int(HelpdeskSettings.load().sla_warning_percent)
            return queryset.filter(sla.at_risk_q(now, share)).exclude(sla.breached_q(now))
        if self.value() == "none":
            return queryset.filter(response_due_at__isnull=True, resolution_due_at__isnull=True)
        return queryset


class UnreadFilter(admin.SimpleListFilter):
    title = "unread"
    parameter_name = "unread"

    def lookups(self, request, model_admin):
        return (("yes", "Unread customer message"),)

    def queryset(self, request, queryset):
        return queryset.filter(unread=True) if self.value() == "yes" else queryset


class PriorityFilter(admin.SimpleListFilter):
    """Priorities from the most severe (the stored values do not sort by severity)."""

    title = "priority"
    parameter_name = "priority"

    def lookups(self, request, model_admin):
        labels = dict(Ticket.Priority.choices)
        return [(value, labels[value]) for value in SEVERITY]

    def queryset(self, request, queryset):
        return queryset.filter(priority=self.value()) if self.value() in Ticket.Priority.values else queryset
