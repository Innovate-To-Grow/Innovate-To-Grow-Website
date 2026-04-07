from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from core.models import ProjectControlModel
from mail.login_redirects import is_safe_internal_redirect_path

AUDIENCE_CHOICES = [
    ("subscribers", "All Email Subscribers"),
    ("event_registrants", "Event Registrants"),
    ("selected_members", "Selected Members"),
    ("manual", "Manual Emails"),
]

# Extended choices used by the admin form — kept separate so the model field
# definition stays unchanged and no migration is needed.
ALL_AUDIENCE_CHOICES = [
    ("subscribers", "All Email Subscribers"),
    ("event_registrants", "Event Registrants"),
    ("ticket_type", "Event Ticket Type"),
    ("checked_in", "Checked-In Attendees"),
    ("not_checked_in", "No-Shows (Not Checked In)"),
    ("all_members", "All Active Members"),
    ("staff", "Staff Members"),
    ("selected_members", "Selected Members"),
    ("manual", "Manual Emails"),
]

_ALL_AUDIENCE_LABELS = dict(ALL_AUDIENCE_CHOICES)

MEMBER_EMAIL_CHOICES = [
    ("primary", "Primary email only"),
    ("all", "All emails (primary + secondary)"),
]

STATUS_CHOICES = [
    ("draft", "Draft"),
    ("sending", "Sending"),
    ("sent", "Sent"),
    ("failed", "Failed"),
]


class EmailCampaign(ProjectControlModel):
    name = models.CharField(max_length=200, blank=True, default="")
    subject = models.CharField(max_length=998)
    body = models.TextField(verbose_name="Email Content", blank=True, default="")
    login_redirect_path = models.CharField(
        max_length=200,
        verbose_name="Post-login destination",
        help_text="Internal site page where recipients land after one-click login.",
    )

    audience_type = models.CharField(max_length=32, choices=AUDIENCE_CHOICES, default="subscribers")
    event = models.ForeignKey(
        "event.Event",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="email_campaigns",
        help_text="Required when audience is 'Event Registrants'.",
    )
    selected_members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="selected_campaigns",
        help_text="Pick members when audience is 'Selected Members'.",
    )
    member_email_scope = models.CharField(
        max_length=16,
        choices=MEMBER_EMAIL_CHOICES,
        default="primary",
        verbose_name="Send to",
        help_text="Send to primary email only, or all emails for each member.",
    )
    manual_emails = models.TextField(
        blank=True,
        default="",
        help_text="One email per line. Used when audience is 'Manual Emails'.",
    )

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="draft")
    total_recipients = models.PositiveIntegerField(default=0)
    sent_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    sent_at = models.DateTimeField(null=True, blank=True)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Amazon SES Mail"
        verbose_name_plural = "Amazon SES Mails"

    def get_audience_type_display(self):
        return _ALL_AUDIENCE_LABELS.get(self.audience_type, self.audience_type)

    def __str__(self):
        label = self.name or self.subject[:60] or "Untitled"
        return f"{label} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        if not self.name:
            self.name = self.subject[:200] if self.subject else "Untitled"
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if not is_safe_internal_redirect_path(self.login_redirect_path):
            raise ValidationError({"login_redirect_path": "Please select a valid internal destination."})
        event_required_types = ("event_registrants", "ticket_type", "checked_in", "not_checked_in")
        if self.audience_type in event_required_types and not self.event_id:
            raise ValidationError(
                {"event": f"An event must be selected for the '{self.get_audience_type_display()}' audience."}
            )
        if self.audience_type == "ticket_type" and not self.manual_emails.strip():
            raise ValidationError({"manual_emails": "A ticket type must be selected."})
        if self.audience_type == "manual" and not self.manual_emails.strip():
            raise ValidationError({"manual_emails": "Please enter at least one email address."})
