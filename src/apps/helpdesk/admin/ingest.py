"""Helpdesk → Ingest problems: inbound queue rows that did not become (part of) a ticket, with a Retry action.

It opens on the problems (failed after the last attempt, or skipped because the message was gone or came from a
mailbox the site no longer reads); the Status filter also shows the rest of the queue. Read-only: Retry puts the
selected problems back in the queue and wakes the ingest. Nothing is ever dropped silently.
"""

from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html
from unfold.decorators import action, display

from apps.core.admin import BaseModelAdmin
from apps.core.models import InboundMessage
from apps.core.services.email.inbound import LABELS, consume

from ..models import IngestRecord, Ticket
from ..services.ingest import jobs

Status = InboundMessage.Status
PROBLEMS = (Status.FAILED, Status.SKIPPED)
STATUS_COLORS = {Status.FAILED: "danger", Status.SKIPPED: "warning", Status.DONE: "success"}


class ProblemFilter(admin.SimpleListFilter):
    title = "status"
    parameter_name = "state"

    def lookups(self, request, model_admin):
        return (("problems", "Problems (default)"), *Status.choices, ("all", "Everything"))

    def choices(self, changelist):
        current = self.value() or "problems"
        for lookup, title in self.lookup_choices:
            yield {
                "selected": current == lookup,
                "query_string": changelist.get_query_string({self.parameter_name: lookup}),
                "display": title,
            }

    def queryset(self, request, queryset):
        current = self.value() or "problems"
        if current == "problems":
            return queryset.filter(status__in=PROBLEMS)
        if current in Status.values:
            return queryset.filter(status=current)
        return queryset


@admin.register(IngestRecord)
class IngestRecordAdmin(BaseModelAdmin):
    require_confirmation = False
    list_display = (
        "received_at",
        "from_address",
        "subject",
        "status_column",
        "attempts",
        "last_error",
        "classification_column",
        "ticket_column",
    )
    list_filter = (ProblemFilter, "classification", "kind")
    search_fields = ("from_address", "subject", "internet_message_id")
    ordering = ("-received_at",)
    actions = ("retry",)
    readonly_fields = (
        "mailbox",
        "received_at",
        "from_address",
        "from_name",
        "subject",
        "kind",
        "status",
        "attempts",
        "next_attempt_at",
        "last_error",
        "classification",
        "subtype",
        "result",
        "processed_at",
        "internet_message_id",
        "conversation_id",
    )
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @display(description="Status", label=STATUS_COLORS, ordering="status")
    def status_column(self, obj):
        return obj.status, obj.get_status_display()

    @display(description="Classification", ordering="classification")
    def classification_column(self, obj):
        return LABELS.get(obj.classification, obj.classification or "—")

    @display(description="Ticket")
    def ticket_column(self, obj):
        number = (obj.result or {}).get("ticket")
        ticket = Ticket.objects.filter(number=number).only("pk", "number").first() if number else None
        if ticket is None:
            return "—"
        return format_html('<a href="{}">{}</a>', reverse("admin:helpdesk_ticket_change", args=[ticket.pk]), ticket)

    @action(description="Retry: import again")
    def retry(self, request, queryset):
        count = consume.requeue(queryset)
        if count:
            jobs.ensure_scheduled()
        messages.success(request, f"{count} message{'s' if count != 1 else ''} queued again for import.")
