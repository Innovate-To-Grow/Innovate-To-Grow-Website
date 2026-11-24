"""The ticket queue: which tickets it lists and how, and its columns."""

from django.db.models import Count, Q
from django.utils.html import format_html
from unfold.decorators import display

from ...models import Ticket, TicketMessage
from ...services import tickets
from ...services.tickets import numbering

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
EDITABLE = ("status", "priority", "category", "assignee")


class TicketQueueMixin:
    """The list section of ``TicketAdmin``: the queryset, search, form and columns."""

    # --- list ------------------------------------------------------------------------------------------------------

    def get_queryset(self, request):
        inbound = Q(messages__kind__in=TicketMessage.INBOUND_KINDS)
        return super().get_queryset(request).annotate(inbound_count=Count("messages", filter=inbound))

    def get_search_results(self, request, queryset, search_term):
        """The usual search, plus the ticket whose number was typed ("1234", "#1234" or "I2G-#1234")."""
        results, may_have_duplicates = super().get_search_results(request, queryset, search_term)
        number = numbering.parse_number(search_term)
        if number is not None:
            results = results | queryset.filter(number=number)
        return results, may_have_duplicates

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        assignee = form.base_fields.get("assignee")
        if assignee is not None:
            # Admins, and whoever holds this ticket now (so the page still saves after they stop being one).
            allowed = {member.pk for member in tickets.helpdesk_staff()}
            if obj is not None and obj.assignee_id:
                allowed.add(obj.assignee_id)
            assignee.queryset = assignee.queryset.filter(pk__in=allowed)
        status = form.base_fields.get("status")
        if status is not None:
            # Only a merge makes a ticket merged (it moves the messages and links the ticket it went into).
            status.choices = [choice for choice in status.choices if choice[0] != Status.MERGED]
        return form

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if obj is not None and obj.status == Status.MERGED:
            # A merge is final: the ticket's messages are on the one it was merged into, where its mail goes too.
            return (*fields, "status")
        return fields

    @display(description="Ticket", ordering="number")
    def number_column(self, obj):
        return obj.display_number

    @display(description="Subject")
    def subject_column(self, obj):
        dot = format_html('<span class="i2g-helpdesk-unread" title="Unread">●</span> ') if obj.unread else ""
        return format_html("{}{}", dot, obj.subject or "(no subject)")

    @display(description="Requester", ordering="requester_email")
    def requester_column(self, obj):
        member = " (member)" if obj.requester_member_id else ""
        return f"{obj.requester_name or obj.requester_email}{member}"

    @display(description="Status", label=STATUS_COLORS, ordering="status")
    def status_column(self, obj):
        return obj.status, obj.get_status_display()

    @display(description="Priority", label=PRIORITY_COLORS, ordering="priority")
    def priority_column(self, obj):
        return obj.priority, obj.get_priority_display()

    @display(description="Messages", ordering="inbound_count")
    def message_count(self, obj):
        return getattr(obj, "inbound_count", 0)
