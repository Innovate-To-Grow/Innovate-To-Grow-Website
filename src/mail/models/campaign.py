from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from core.models import ProjectControlModel

AUDIENCE_CHOICES = [
    ("subscribers", "All Email Subscribers"),
    ("event_registrants", "Event Registrants"),
    ("selected_members", "Selected Members"),
    ("manual", "Manual Emails"),
]

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

    def __str__(self):
        label = self.name or self.subject[:60] or "Untitled"
        return f"{label} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        if not self.name:
            self.name = self.subject[:200] if self.subject else "Untitled"
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.audience_type == "event_registrants" and not self.event_id:
            raise ValidationError({"event": "An event must be selected for the 'Event Registrants' audience."})
        if self.audience_type == "manual" and not self.manual_emails.strip():
            raise ValidationError({"manual_emails": "Please enter at least one email address."})
