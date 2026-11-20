"""The ticket queue: which tickets it lists and how, its columns and their sort orders, and the ticket form's choices.

Priority and status sort in their order of severity and of the ticket's life, not alphabetically by stored value; the
SLA column sorts by the due time of the clock that runs now. A ticket number typed in the search ("1234", "#1234" or
"I2G-#1234") finds that ticket whatever the filters, listed first.
"""

from datetime import UTC, datetime

from django.db.models import Case, Count, F, IntegerField, Q, Value, When
from django.db.models.functions import Coalesce, NullIf
from django.utils import timezone
from django.utils.html import format_html
from unfold.decorators import display

from ...models import HelpdeskSettings, Ticket, TicketMessage
from ...services import sla, tickets
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
# The due time of the clock the SLA column shows (the response until it is met); tickets without a clock sort last.
SLA_DUE = Coalesce(
    Case(When(first_responded_at__isnull=True, then=F("response_due_at")), default=F("resolution_due_at")),
    Value(datetime(9999, 12, 31, tzinfo=UTC)),
)
REQUESTER = Coalesce(NullIf("requester_name", Value("")), "requester_email")
RELATED = ("category", "assignment_group", "assignee")


class TicketQueueMixin:
    """The list section of ``TicketAdmin``: the queryset, search, ordering, form choices and columns."""

    form = TicketForm

    def get_queryset(self, request):
        inbound = Q(messages__kind__in=TicketMessage.INBOUND_KINDS)
        # The SLA column's "at risk" share, read once per list (the admin instance is shared between requests).
        warning = Value(int(HelpdeskSettings.load().sla_warning_percent), output_field=IntegerField())
        return (
            super()
            .get_queryset(request)
            .annotate(inbound_count=Count("messages", filter=inbound), sla_warning_percent=warning)
        )

    def get_list_display(self, request):
        # Last activity says more than the creation time the shared timestamp mixin adds.
        return [name for name in super().get_list_display(request) if name != "created_at"]

    def get_search_results(self, request, queryset, search_term):
        """The usual search, plus the ticket whose number was typed, from all tickets (a closed or automated one too)."""
        results, may_have_duplicates = super().get_search_results(request, queryset, search_term)
        number = numbering.parse_number(search_term)
        if number is not None:
            results = results | self.get_queryset(request).filter(number=number)
            may_have_duplicates = True
        return results, may_have_duplicates

    def get_ordering(self, request):
        ordering = list(super().get_ordering(request) or ())
        number = numbering.parse_number(request.GET.get("q", ""))
        if number is not None:
            ordering.insert(0, Case(When(number=number, then=Value(0)), default=Value(1)).asc())
        return ordering

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        assignee = form.base_fields.get("assignee")
        if assignee is not None:
            # Staff who may work tickets, and whoever holds this one now (so the page still saves after a grant ends).
            allowed = {member.pk for member in tickets.helpdesk_staff()}
            if obj is not None and obj.assignee_id:
                allowed.add(obj.assignee_id)
            assignee.queryset = assignee.queryset.filter(pk__in=allowed).order_by("first_name", "last_name")
        for name, current in (
            ("assignment_group", obj.assignment_group_id if obj is not None else None),
            ("category", obj.category_id if obj is not None else None),
        ):
            field = form.base_fields.get(name)
            if field is not None:
                field.queryset = field.queryset.filter(Q(is_active=True) | Q(pk=current))
        for name in RELATED:
            # Groups, categories and members are set up on their own pages, not from a ticket (whose trash icon would
            # delete the group or category for every ticket).
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

    @display(description="Group", ordering="assignment_group__name")
    def group_column(self, obj):
        return obj.assignment_group.name if obj.assignment_group_id else "—"

    @display(description="Assigned to", ordering="assignee__first_name")
    def assignee_column(self, obj):
        if obj.assignee_id is None:
            return "—"
        return obj.assignee.get_full_name() or str(obj.assignee)

    @display(description="Messages", ordering="inbound_count")
    def message_count(self, obj):
        return getattr(obj, "inbound_count", 0)
