"""The audit trail of a ticket: every change of its fields, by whom (null = the system), from what to what."""

from django.conf import settings
from django.db import models

from apps.core.models import ProjectControlModel

from .ticket import Ticket


class TicketEvent(ProjectControlModel):
    class Kind(models.TextChoices):
        CREATED = "created", "Ticket created"
        CUSTOMER_MESSAGE = "customer_message", "Customer message"
        AUTOMATED_MESSAGE = "automated_message", "Automated message attached"
        NOTE = "note", "Internal note"
        STATUS = "status", "Status changed"
        PRIORITY = "priority", "Priority changed"
        CATEGORY = "category", "Category changed"
        ASSIGNED = "assigned", "Assignee changed"
        REOPENED = "reopened", "Reopened"
        MERGED = "merged", "Merged"
        SPAM = "spam", "Marked as spam"
        RECLASSIFIED = "reclassified", "Moved to the queue"
        RELATED = "related", "Related ticket"
        FLOOD = "flood", "Grouped (many messages from one sender)"
        MENTION = "mention", "Mentions another ticket"

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="helpdesk_events"
    )
    kind = models.CharField(max_length=24, choices=Kind.choices, db_index=True)
    data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Ticket Event"
        verbose_name_plural = "Ticket Events"

    def __str__(self):
        return f"{self.get_kind_display()} ({self.ticket_id})"
