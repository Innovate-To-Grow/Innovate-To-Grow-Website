"""How tickets are worked, ServiceNow style: categories, SLA targets per priority, response templates, and the
impact / urgency scale and resolution codes a ticket uses.

- Tickets have no owner (I2G-HELPDESK-01): every Admin works every ticket. **Assignment groups** and a category's
  default group are deprecated: nothing reads, writes or offers them, but their rows stay (the tables, the members
  of each group, the groups tickets had) so no data is lost and a release still running during a deploy keeps
  working. A category that tickets still use cannot be deleted: it is switched off instead.
- An **SLA target** says, for one priority, how long the first response and the resolution may take. A ticket's
  clock starts when its first message arrived; the resolution clock pauses while the ticket waits for the requester
  and while it is resolved or closed (``services.sla``). Calendar time, not business hours.
- A **response template** is a canned reply. Placeholders (``{ticket}``, ``{requester_name}``, ``{subject}``,
  ``{agent_name}``) are replaced when it is inserted into the reply form; nothing else in it is interpreted.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import ProjectControlModel

# Minutes in a day / an hour, for readable defaults.
HOUR = 60
DAY = 24 * HOUR


class Level(models.IntegerChoices):
    """Impact and urgency: 1 is the highest."""

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


class TicketCategory(ProjectControlModel):
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)
    default_group = models.ForeignKey(  # deprecated (I2G-HELPDESK-01): kept with its data, never read or offered
        "helpdesk.AssignmentGroup",
        null=True,
        blank=True,
        editable=False,
        on_delete=models.PROTECT,
        related_name="default_for_categories",
        help_text="Deprecated: tickets have no owner.",
    )

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "Ticket Category"
        verbose_name_plural = "Ticket Categories"

    def __str__(self):
        return self.name


class AssignmentGroup(ProjectControlModel):
    """Deprecated (I2G-HELPDESK-01): kept with its rows, with no admin page; nothing reads or writes it."""

    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255, blank=True, default="")
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="helpdesk_groups",
        help_text="Deprecated: tickets have no owner.",
    )
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="helpdesk_managed_groups",
    )
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "Assignment Group"
        verbose_name_plural = "Assignment Groups"

    def __str__(self):
        return self.name


class SLATarget(ProjectControlModel):
    """The response and resolution targets of one priority (one row per priority)."""

    priority = models.CharField(max_length=8, unique=True, help_text="The ticket priority this target applies to.")
    response_minutes = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(90 * DAY)],
        help_text="Minutes until the first response is due (a reply sent from the ticket, or staff moving it out of "
        "New).",
    )
    resolution_minutes = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(365 * DAY)],
        help_text="Minutes until the ticket should be resolved, not counting the time it waits for the requester.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Off: new tickets of this priority (and tickets moved to it) get no SLA; clocks already "
        "running keep their due times.",
    )

    class Meta:
        ordering = ["priority"]
        verbose_name = "SLA Target"
        verbose_name_plural = "SLA Targets"

    def __str__(self):
        from .ticket import Ticket

        return f"SLA for {dict(Ticket.Priority.choices).get(self.priority, self.priority)}"

    def clean(self):
        super().clean()
        if self.response_minutes and self.resolution_minutes and self.response_minutes > self.resolution_minutes:
            raise ValidationError({"response_minutes": "The first response cannot be due after the resolution."})


class ResponseTemplate(ProjectControlModel):
    name = models.CharField(max_length=100, unique=True)
    body = models.TextField(
        help_text="The reply text. {ticket}, {requester_name}, {subject} and {agent_name} are replaced when the "
        "template is inserted; edit the text before sending."
    )
    category = models.ForeignKey(
        "helpdesk.TicketCategory",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="response_templates",
        help_text="Listed first on tickets of this category (every active template is offered).",
    )
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "Response Template"
        verbose_name_plural = "Response Templates"

    def __str__(self):
        return self.name
