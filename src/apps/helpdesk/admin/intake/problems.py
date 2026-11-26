"""Helpdesk → Ingest problems: inbound queue rows that did not become (part of) a ticket, with Retry and Dismiss.

It opens on the problems (failed after the last attempt, or skipped because the message was gone or came from a
mailbox the site no longer reads); the Status filter also shows the rest of the queue. Read-only: Retry puts the
selected problems back in the queue and wakes the ingest. Dismiss (handled) takes a problem that can never be imported
(a message deleted in Outlook first) out of the Problems view: the row keeps its status and error (the dismissal is a
``result`` entry, no column of its own), the Dismissed and Everything filters still list it, retention removes it like
any other row, and Retry clears the dismissal. Both write an admin-history entry on each row they change and say why
they left the others as they were. Nothing is ever dropped silently.
"""

from django.contrib import admin, messages
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from unfold.decorators import action, display

from apps.core.admin import BaseModelAdmin
from apps.core.models import InboundMessage
from apps.core.services.email.inbound import LABELS
from apps.core.services.email.inbound.processing import consume

from ...models import IngestRecord, Ticket
from ...services.ingest.pipeline import jobs

Status = InboundMessage.Status
PROBLEMS = (Status.FAILED, Status.SKIPPED)
DISMISSED = "dismissed"  # the ``result`` key of a dismissed problem: who dismissed it, and when
STATUS_COLORS = {Status.FAILED: "danger", Status.SKIPPED: "warning", Status.DONE: "success", DISMISSED: "info"}


def _messages(count: int) -> str:
    return f"{count} message{'s' if count != 1 else ''}"


def _left(skipped: int, why: str) -> str:
    return f" {skipped} left as {'it was' if skipped == 1 else 'they were'}: {why}" if skipped else ""


def _retry(row: InboundMessage) -> str:
    """Queue one problem again: its admin-history entry, or "" when it is none (or no longer one). A retried message
    that fails again is a problem again, so its dismissal goes with the retry."""
    with transaction.atomic():
        if not consume.requeue(InboundMessage.objects.filter(pk=row.pk)):
            return ""
        if DISMISSED not in (row.result or {}):
            return "Retried: queued again for import."
        kept = {key: value for key, value in row.result.items() if key != DISMISSED}
        InboundMessage.objects.filter(pk=row.pk).update(result=kept)
    return "Retried: queued again for import. Its dismissal was cleared."


def _dismiss(row: InboundMessage, stamp: dict) -> bool:
    """Mark one problem dismissed; False when it is none (or dismissed already). The update checks the row's status
    again, so a message retried since the list was shown is left to the ingest."""
    if row.status not in PROBLEMS or DISMISSED in (row.result or {}):
        return False
    result = {**(row.result or {}), DISMISSED: stamp}
    updated = InboundMessage.objects.filter(pk=row.pk, status=row.status).update(
        result=result, updated_at=timezone.now()
    )
    return bool(updated)


class ProblemFilter(admin.SimpleListFilter):
    title = "status"
    parameter_name = "state"

    def lookups(self, request, model_admin):
        return (
            ("problems", "Problems (default)"),
            *Status.choices,
            (DISMISSED, "Dismissed (handled)"),
            ("all", "Everything"),
        )

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
            return queryset.filter(status__in=PROBLEMS).exclude(result__has_key=DISMISSED)
        if current == DISMISSED:
            return queryset.filter(result__has_key=DISMISSED)
        if current in Status.values:
            return queryset.filter(status=current)
        return queryset


class ClassificationFilter(admin.SimpleListFilter):
    """The classifications under the names the list's column gives them (a row not imported yet has none)."""

    title = "classification"
    parameter_name = "classification"

    def lookups(self, request, model_admin):
        return tuple(LABELS.items())

    def queryset(self, request, queryset):
        return queryset.filter(classification=self.value()) if self.value() else queryset


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
    list_filter = (ProblemFilter, ClassificationFilter, "kind")
    search_fields = ("from_address", "subject", "internet_message_id")
    ordering = ("-received_at",)
    actions = ("retry", "dismiss")
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
        if DISMISSED in (obj.result or {}):
            return DISMISSED, f"{obj.get_status_display()}, dismissed"
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
        # Taken first: on the Dismissed view the list's own filter would lose them once their dismissal goes.
        chosen = list(self.model.objects.filter(pk__in=list(queryset.values_list("pk", flat=True))))
        retried = [(row, entry) for row in chosen if (entry := _retry(row))]
        for row, entry in retried:
            self.log_change(request, row, entry)
        if retried:
            jobs.ensure_scheduled()
        why = "only failed or skipped messages are retried."
        text = f"{_messages(len(retried))} queued again for import.{_left(len(chosen) - len(retried), why)}"
        (messages.success if retried else messages.warning)(request, text)

    @action(description="Dismiss (handled)")
    def dismiss(self, request, queryset):
        chosen = list(queryset)
        stamp = {"by": request.user.get_full_name() or str(request.user), "at": timezone.now().isoformat()}
        dismissed = [row for row in chosen if _dismiss(row, stamp)]
        for row in dismissed:
            self.log_change(request, row, "Dismissed as handled (bulk action).")
        count, skipped = len(dismissed), len(chosen) - len(dismissed)
        listed = f"; the Dismissed and Everything filters still list {'it' if count == 1 else 'them'}" if count else ""
        why = "only failed or skipped messages not dismissed yet are dismissed."
        text = f"{_messages(count)} dismissed as handled{listed}.{_left(skipped, why)}"
        (messages.success if count else messages.warning)(request, text)
