"""The ticket queue: which tickets it lists and how, its columns and their sort orders, and the ticket form's choices.

Priority and status sort in their order of severity and of the ticket's life, not alphabetically by stored value; the
SLA column sorts as it reads: breaches first, then running clocks by their due time, then paused clocks, then
tickets that are done or have no clock. A ticket number typed in the search ("1234", "#1234" or "I2G-#1234")
finds that ticket whatever the filters, listed first unless a column sort is chosen.

Tickets have no owner (I2G-HELPDESK-01): instead of an assignee, the "Last reply" column says who replied to the
requester last and when (``outbound.activity``), so two people do not answer the same ticket unknowingly.
"""

from datetime import UTC, datetime

from django.db.models import Case, Count, DateTimeField, F, IntegerField, Q, Value, When
from django.db.models.functions import Coalesce, NullIf
from django.utils import timezone
from django.utils.html import format_html
from unfold.decorators import display

from ...models import HelpdeskSettings, Ticket, TicketMessage
from ...services import sla
from ...services.outbound import activity
from ...services.sla.priority import PRIORITY_RANK
from ...services.tickets import numbering
from .form import TicketForm

Status = Ticket.Status
STATUS_COLORS = {
    Status.NEW: "info",
    Status.OPEN: "warning",
    Status.PENDING_CUSTOMER: "info",
    Status.PENDING_INTERNAL: "info",
    Status.RESOLVED: "success",
    Status.CLOSED: "success",
    Status.MERGED: "info",
    Status.SPAM: "danger",
}
PRIORITY_COLORS = {"low": "info", "normal": "info", "high": "warning", "urgent": "danger"}
SLA_COLORS = {
    "none": "info",
    "running": "info",
    "paused": "info",
    "met": "success",
    "at_risk": "warning",
    "breached": "danger",
}


def _rank(field: str, order) -> Case:
    return Case(
        *(When(**{field: value}, then=Value(index)) for index, value in enumerate(order)),
        default=Value(len(order)),
        output_field=IntegerField(),
    )


STATUS_RANK = _rank("status", (*Ticket.OPEN_STATUSES, Status.RESOLVED, Status.CLOSED, Status.MERGED, Status.SPAM))
# What the SLA column sorts by: a breach first, then the due time of the clock it shows (the response until it is
# met), a paused resolution clock after every running one, and last tickets that are done or have no clock.
_FIRST, _PAUSED, _LAST = (Value(datetime(year, 1, 1, tzinfo=UTC)) for year in (1970, 9998, 9999))
SLA_DUE = Case(
    When(Q(response_breached=True) | Q(resolution_breached=True), then=_FIRST),
    When(Q(sla_started_at__isnull=True) | ~Q(status__in=Ticket.OPEN_STATUSES), then=_LAST),
    When(first_responded_at__isnull=True, then=Coalesce(F("response_due_at"), _LAST)),
    When(sla_paused_at__isnull=False, then=_PAUSED),
    default=Coalesce(F("resolution_due_at"), _LAST),
    output_field=DateTimeField(),
)
REQUESTER = Coalesce(NullIf("requester_name", Value("")), "requester_email")
RELATED = ("category",)


class TicketQueueMixin:
    """The list section of ``TicketAdmin``: the queryset, search, ordering, form choices and columns."""

    form = TicketForm

    def get_queryset(self, request):
        inbound = Q(messages__kind__in=TicketMessage.INBOUND_KINDS)
        # The SLA column's "at risk" share, read once per list (the admin instance is shared between requests).
        warning = Value(int(HelpdeskSettings.load().sla_warning_percent), output_field=IntegerField())
        queryset = super().get_queryset(request)
        queryset = queryset.annotate(inbound_count=Count("messages", filter=inbound), sla_warning_percent=warning)
        return activity.with_last_reply(queryset)

    def get_list_display(self, request):
        # Last activity says more than the creation time the shared timestamp mixin adds.
        return [name for name in super().get_list_display(request) if name != "created_at"]

    def get_search_results(self, request, queryset, search_term):
        """The usual search, plus the ticket whose number was typed, from all tickets (a closed or automated one too)."""
        results, may_have_duplicates = super().get_search_results(request, queryset, search_term)
        number = numbering.parse_number(search_term)
        if number is not None:
            # A fresh queryset: the filters' joins stay in the subquery (no doubled counts). The list is ordered before
            # it is searched, so its order (a sorted column, or the default) is kept behind the number match.
            found = Q(pk__in=results.values("pk")) | Q(number=number)
            first = Case(When(number=number, then=Value(0)), default=Value(1)).asc()
            results = self.get_queryset(request).filter(found).order_by(first, *queryset.query.order_by)
            may_have_duplicates = False
        return results, may_have_duplicates

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        field = form.base_fields.get("category")
        if field is not None:
            current = obj.category_id if obj is not None else None
            field.queryset = field.queryset.filter(Q(is_active=True) | Q(pk=current))
            field.label_from_instance = lambda item: str(item) if item.is_active else f"{item} (inactive)"
        for name in RELATED:
            # Categories are set up on their own page, not from a ticket (whose trash icon would delete the category
            # for every ticket).
            widget = getattr(form.base_fields.get(name), "widget", None)
            for flag in ("can_add_related", "can_change_related", "can_delete_related", "can_view_related"):
                if hasattr(widget, flag):
                    setattr(widget, flag, False)
        return form

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if obj is not None and (obj.status == Status.MERGED or obj.is_automated_or_spam):
            # A merge is final; automated mail and spam become a person's ticket with "Not automated: move to the
            # queue" (which starts its SLA), not by reopening it here.
            return (*fields, "status")
        return fields

    @display(description="Ticket", ordering="number")
    def number_column(self, obj):
        return obj.display_number

    @display(description="Subject", ordering="subject")
    def subject_column(self, obj):
        dot = format_html('<span class="i2g-helpdesk-unread" title="Unread">●</span> ') if obj.unread else ""
        return format_html("{}{}", dot, obj.subject or "(no subject)")

    @display(description="Requester", ordering=REQUESTER)
    def requester_column(self, obj):
        member = " (member)" if obj.requester_member_id else ""
        return f"{obj.requester_name or obj.requester_email}{member}"

    @display(description="Status", label=STATUS_COLORS, ordering=STATUS_RANK)
    def status_column(self, obj):
        return obj.status, obj.get_status_display()

    @display(description="Priority", label=PRIORITY_COLORS, ordering=PRIORITY_RANK)
    def priority_column(self, obj):
        return obj.priority, obj.get_priority_display()

    @display(description="SLA", label=SLA_COLORS, ordering=SLA_DUE)
    def sla_column(self, obj):
        warning = getattr(obj, "sla_warning_percent", None) or int(HelpdeskSettings.load().sla_warning_percent)
        return sla.queue_label(obj, timezone.now(), warning)

    @display(description="Last reply", ordering="last_reply_at")
    def last_reply_column(self, obj):
        """Who replied to the requester last and when ("—": nobody yet)."""
        at = getattr(obj, "last_reply_at", None)
        if at is None:
            return "—"
        by = getattr(obj, "last_reply_by", "") or "a former staff member"
        return format_html(
            '{}<br><span class="i2g-helpdesk-muted">{}</span>', by, timezone.localtime(at).strftime("%b %d, %H:%M")
        )

    @display(description="Last reply")
    def last_reply_display(self, obj):
        """The ticket page's line: who replied to the requester last and when (every Admin works every ticket)."""
        return activity.last_reply_text(obj)

    @display(description="Messages", ordering="inbound_count")
    def message_count(self, obj):
        return getattr(obj, "inbound_count", 0)
