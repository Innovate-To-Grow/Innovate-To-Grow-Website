"""Tickets and their categories.

A ticket is opened by the first message of a conversation that reaches the mailbox; later messages of the same
conversation join it (``services.ingest.routing.matching``). Automated mail (out-of-office replies, bounce reports, receipts,
list mail, spam, the site's own messages) opens a ticket that is closed at once and hidden from the default queue
(``automated``): it raises no notification, has no response target and never reopens. Every link to a member or a
campaign is ``SET_NULL``, so a ticket outlives a deleted account and keeps the requester's address.

Nothing is ever merged into automated mail or spam (``is_automated_or_spam``): ``services.tickets.merge`` refuses
it, and ``clean`` refuses such a ``merged_into`` for any form or ``full_clean()`` path.

Tickets are worked ServiceNow style: the priority follows from impact and urgency (``services.tickets.priority``), a
ticket has an assignment group and an assignee within it, its SLA clock gives a response and a resolution due time
(``services.tickets.sla``), and resolving it records a resolution code and notes. New columns carry database
defaults, so the previous release keeps inserting tickets while a deploy rolls out.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.models import ProjectControlModel

TICKET_PREFIX = "I2G-#"


class TicketCategory(ProjectControlModel):
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)
    default_group = models.ForeignKey(
        "helpdesk.AssignmentGroup",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="default_for_categories",
        help_text="Assignment rule: a ticket given this category while it has no group is assigned to this group.",
    )

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "Ticket Category"
        verbose_name_plural = "Ticket Categories"

    def __str__(self):
        return self.name


class Ticket(ProjectControlModel):
    class Status(models.TextChoices):
        NEW = "new", "New"
        OPEN = "open", "In progress"
        PENDING_CUSTOMER = "pending_customer", "On hold – awaiting requester"
        PENDING_INTERNAL = "pending_internal", "On hold – awaiting internal"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"
        MERGED = "merged", "Merged"
        SPAM = "spam", "Spam"

    class Priority(models.TextChoices):
        # The stored values predate the ServiceNow labels; the order of severity is urgent, high, normal, low.
        LOW = "low", "4 – Low"
        NORMAL = "normal", "3 – Moderate"
        HIGH = "high", "2 – High"
        URGENT = "urgent", "1 – Critical"

    class Impact(models.IntegerChoices):
        HIGH = 1, "1 – High"
        MEDIUM = 2, "2 – Medium"
        LOW = 3, "3 – Low"

    class Urgency(models.IntegerChoices):
        HIGH = 1, "1 – High"
        MEDIUM = 2, "2 – Medium"
        LOW = 3, "3 – Low"

    class ResolutionCode(models.TextChoices):
        SOLVED = "solved", "Solved"
        INFORMATION_PROVIDED = "information_provided", "Information provided"
        WORKAROUND = "workaround", "Solved (workaround)"
        REFERRED = "referred", "Referred elsewhere"
        DUPLICATE = "duplicate", "Duplicate"
        NO_ACTION_NEEDED = "no_action_needed", "No action needed"
        RESOLVED_BY_REQUESTER = "resolved_by_requester", "Resolved by requester"
        NOT_SOLVED = "not_solved", "Not solved"

    class Source(models.TextChoices):
        EMAIL = "email", "Email"
        MANUAL = "manual", "Manual"

    OPEN_STATUSES = (Status.NEW, Status.OPEN, Status.PENDING_CUSTOMER, Status.PENDING_INTERNAL)
    # A ticket in one of these was closed by staff (or at once, when automated); ``closed_at`` says when.
    CLOSED_STATUSES = (Status.RESOLVED, Status.CLOSED, Status.MERGED, Status.SPAM)

    number = models.PositiveIntegerField(unique=True, editable=False, help_text="Shown as I2G-#<number>.")
    subject = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW, db_index=True)
    priority = models.CharField(
        max_length=8,
        choices=Priority.choices,
        default=Priority.NORMAL,
        db_index=True,
        help_text="Follows from impact and urgency.",
    )
    impact = models.PositiveSmallIntegerField(
        choices=Impact.choices, default=Impact.MEDIUM, db_default=Impact.MEDIUM, help_text="How many people it affects."
    )
    urgency = models.PositiveSmallIntegerField(
        choices=Urgency.choices,
        default=Urgency.MEDIUM,
        db_default=Urgency.MEDIUM,
        help_text="How soon it must be dealt with.",
    )
    category = models.ForeignKey(
        TicketCategory, null=True, blank=True, on_delete=models.SET_NULL, related_name="tickets"
    )
    assignment_group = models.ForeignKey(
        "helpdesk.AssignmentGroup",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tickets",
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="helpdesk_assigned_tickets",
        verbose_name="assigned to",
    )
    requester_email = models.CharField(max_length=254, blank=True, default="", db_index=True)
    requester_name = models.CharField(max_length=255, blank=True, default="")
    requester_member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="helpdesk_requested_tickets",
        help_text="The member whose contact email sent the first message, when one did.",
    )
    participants = models.JSONField(
        default=list, blank=True, help_text="Every address seen on the ticket's messages, except the site's own."
    )
    campaign = models.ForeignKey(
        "mail.EmailCampaign",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="helpdesk_tickets",
        help_text="The campaign the first message replied to, when its headers name one.",
    )
    related_ticket = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="followed_by",
        help_text="An earlier ticket of the same conversation (closed long ago, automated, or marked spam).",
    )
    merged_into = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="merged_tickets"
    )
    source = models.CharField(max_length=8, choices=Source.choices, default=Source.EMAIL)
    classification = models.CharField(max_length=16, blank=True, default="", db_index=True)
    automated = models.BooleanField(
        default=False, db_index=True, help_text="Automated mail: closed at once and hidden from the default queue."
    )
    flags = models.JSONField(default=list, blank=True)
    unread = models.BooleanField(default=False, db_index=True, help_text="A message arrived that nobody opened yet.")
    backfilled = models.BooleanField(default=False, help_text="Imported from mail received before the helpdesk ran.")
    first_message_at = models.DateTimeField(null=True, blank=True)
    last_activity_at = models.DateTimeField(default=timezone.now, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    resolution_code = models.CharField(
        max_length=24, choices=ResolutionCode.choices, blank=True, default="", db_default=""
    )
    resolution_notes = models.TextField(blank=True, default="", db_default="")
    # The SLA clock (``services.tickets.sla``). No due times: no SLA (automated mail, backfilled mail, an inactive
    # target). The resolution clock does not run while ``sla_paused_at`` is set; the time it stood still is added to
    # the resolution due time when it starts again.
    sla_started_at = models.DateTimeField(null=True, blank=True)
    response_due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    resolution_due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    first_responded_at = models.DateTimeField(null=True, blank=True)
    sla_paused_at = models.DateTimeField(null=True, blank=True)
    sla_paused_seconds = models.PositiveIntegerField(default=0, db_default=0)
    response_breached = models.BooleanField(default=False, db_default=False, db_index=True)
    resolution_breached = models.BooleanField(default=False, db_default=False, db_index=True)

    class Meta:
        ordering = ["-last_activity_at"]
        verbose_name = "Ticket"
        verbose_name_plural = "Tickets"
        indexes = [
            models.Index(fields=["automated", "status", "last_activity_at"], name="helpdesk_ticket_queue_idx"),
            models.Index(fields=["requester_email", "first_message_at"], name="helpdesk_ticket_requester_idx"),
        ]

    def __str__(self):
        return f"{self.display_number}: {self.subject or '(no subject)'}"

    @property
    def display_number(self) -> str:
        return f"{TICKET_PREFIX}{self.number}"

    @property
    def is_open(self) -> bool:
        return self.status in self.OPEN_STATUSES

    @property
    def is_automated_or_spam(self) -> bool:
        """Hidden from the people queue (its "Automated & spam" view); a person's message never joins such a ticket,
        and nothing is merged into one."""
        return self.automated or self.status == self.Status.SPAM

    def clean(self):
        super().clean()
        if not self.merged_into_id:
            return
        stored = Ticket.objects.filter(pk=self.pk).values_list("merged_into_id", flat=True).first()
        if stored == self.merged_into_id:
            return  # a merge made earlier is not judged again (its target may have been marked spam since)
        target = Ticket.objects.filter(pk=self.merged_into_id).first()
        if target is None:
            return  # ``clean_fields`` reports a target that does not exist
        if target.pk == self.pk or target.status == self.Status.MERGED:
            raise ValidationError("A ticket can only be merged into another ticket that is not merged itself.")
        if target.is_automated_or_spam:
            what = "spam" if target.status == self.Status.SPAM else "automated mail"
            raise ValidationError(
                f"Nothing is merged into automated mail or spam, and {target.display_number} is {what}."
            )
