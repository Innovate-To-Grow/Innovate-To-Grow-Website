"""The ticket queue: which tickets it lists and how, its columns, and the ticket form.

The form follows ServiceNow: impact and urgency set the priority (read-only), the assignee is chosen within the
assignment group's members when the ticket has one, and resolving or closing a ticket needs a resolution code.
"""

from django import forms
from django.db.models import Count, IntegerField, Q, Value
from django.utils import timezone
from django.utils.html import format_html
from unfold.decorators import display

from ...models import HelpdeskSettings, Ticket, TicketMessage
from ...services import sla, tickets
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
SLA_COLORS = {
    "none": "info",
    "running": "info",
    "paused": "info",
    "met": "success",
    "at_risk": "warning",
    "breached": "danger",
}
# What the ticket page saves (the priority follows from impact and urgency).
EDITABLE = (
    "status",
    "impact",
    "urgency",
    "category",
    "assignment_group",
    "assignee",
    "resolution_code",
    "resolution_notes",
)
RESOLVING = (Status.RESOLVED, Status.CLOSED)


class TicketForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = "__all__"
        widgets = {"resolution_notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # A form posted without impact or urgency (an older page, a script) keeps the ticket's own values.
        for name in ("impact", "urgency"):
            if name in self.fields:
                self.fields[name].required = False

    def clean(self):
        cleaned = super().clean()
        for name in ("impact", "urgency"):
            if name in self.fields and not cleaned.get(name):
                cleaned[name] = getattr(self.instance, name)
        status = cleaned.get("status", self.instance.status)
        if status in RESOLVING and status != self.instance.status and "resolution_code" in self.fields:
            if not cleaned.get("resolution_code"):
                self.add_error("resolution_code", "Choose a resolution code to resolve or close the ticket.")
        group, assignee = cleaned.get("assignment_group"), cleaned.get("assignee")
        changed = {"assignment_group", "assignee"} & set(self.changed_data)
        if changed and group is not None and assignee is not None and group.members.exists():
            if not group.members.filter(pk=assignee.pk).exists():
                self.add_error("assignee", f"{assignee} is not a member of {group}.")
        return cleaned


class TicketQueueMixin:
    """The list section of ``TicketAdmin``: the queryset, search, form and columns."""

    form = TicketForm

    # --- list ------------------------------------------------------------------------------------------------------

    def get_queryset(self, request):
        inbound = Q(messages__kind__in=TicketMessage.INBOUND_KINDS)
        # The SLA column's "at risk" share, read once per list (the admin instance is shared between requests).
        warning = Value(int(HelpdeskSettings.load().sla_warning_percent), output_field=IntegerField())
        return (
            super()
            .get_queryset(request)
            .annotate(inbound_count=Count("messages", filter=inbound), sla_warning_percent=warning)
        )

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
            # Staff who may work tickets, and whoever holds this one now (so the page still saves after a grant ends).
            allowed = {member.pk for member in tickets.helpdesk_staff()}
            if obj is not None and obj.assignee_id:
                allowed.add(obj.assignee_id)
            assignee.queryset = assignee.queryset.filter(pk__in=allowed)
        group = form.base_fields.get("assignment_group")
        if group is not None:
            current = obj.assignment_group_id if obj is not None else None
            group.queryset = group.queryset.filter(Q(is_active=True) | Q(pk=current))
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

    @display(description="SLA", label=SLA_COLORS)
    def sla_column(self, obj):
        warning = getattr(obj, "sla_warning_percent", None) or int(HelpdeskSettings.load().sla_warning_percent)
        which, clock = sla.current_clock(obj, timezone.now(), warning)
        if clock.state == "none":
            return "none", "—"
        if clock.state in ("running", "at_risk") and clock.due is not None:
            return clock.state, f"{which} due {timezone.localtime(clock.due):%b %d %H:%M}"
        return clock.state, f"{which}: {clock.label}"

    @display(description="Group", ordering="assignment_group__name")
    def group_column(self, obj):
        return obj.assignment_group.name if obj.assignment_group_id else "—"

    @display(description="Messages", ordering="inbound_count")
    def message_count(self, obj):
        return getattr(obj, "inbound_count", 0)
