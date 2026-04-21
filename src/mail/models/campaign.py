from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from core.models import ProjectControlModel
from mail.login_redirects import is_safe_internal_redirect_path

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

# Subset of audience types that can be used as an exclusion group (no "Manual Emails").
EXCLUDE_AUDIENCE_CHOICES = [
    ("", "No exclusion"),
    ("subscribers", "All Email Subscribers"),
    ("event_registrants", "Event Registrants"),
    ("ticket_type", "Event Ticket Type"),
    ("checked_in", "Checked-In Attendees"),
    ("not_checked_in", "No-Shows (Not Checked In)"),
    ("all_members", "All Active Members"),
    ("staff", "Staff Members"),
    ("selected_members", "Selected Members"),
]

MEMBER_EMAIL_CHOICES = [
    ("primary", "Primary email only"),
    ("all", "All emails (primary + secondary + other)"),
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
        default="/account",
        verbose_name="Post-login destination",
        help_text="Internal site page where recipients land after one-click login.",
    )

    audience_type = models.CharField(max_length=32, choices=ALL_AUDIENCE_CHOICES, default="subscribers")
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
        help_text=(
            "For member-based audiences (subscribers, all active members, staff, selected members): "
            "send only to each person's primary contact email, or to every saved contact email "
            "(primary, secondary, and other). Event-based audiences (registrants, ticket, checked-in, "
            "no-shows) use the registration's attendee email when set, otherwise the member's primary email."
        ),
    )
    exclude_member_email_scope = models.CharField(
        max_length=16,
        choices=MEMBER_EMAIL_CHOICES,
        default="primary",
        verbose_name="Send to",
        help_text=(
            "When the exclude audience is member-based, which of each person's contact emails are used to "
            "match against the main recipient list (primary only, or primary + secondary + other). "
            "Ignored for event-based exclude audiences (they use attendee or primary as for registrations)."
        ),
    )
    manual_emails = models.TextField(
        blank=True,
        default="",
        help_text="One email per line. Used when audience is 'Manual Emails'.",
    )

    exclude_audience_type = models.CharField(
        max_length=32,
        choices=EXCLUDE_AUDIENCE_CHOICES,
        blank=True,
        default="",
        verbose_name="Exclude audience",
        help_text=(
            "Remove anyone whose address appears in this group from the final list (case-insensitive). "
            'For member-based exclusions, addresses follow the second "Send to" field below. '
            "For event-based exclusions, each registration's attendee email, or the member's primary email "
            "if the attendee email is empty."
        ),
    )
    exclude_event = models.ForeignKey(
        "event.Event",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Event used to build the exclusion list when the exclude audience is event-based.",
    )
    exclude_ticket_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Ticket UUID when exclude audience is 'Event Ticket Type' (same format as primary ticket campaigns).",
    )
    exclude_members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="+",
        help_text=(
            'When exclude audience is "Selected Members", pick members here; the exclude "Send to" '
            "field controls which of their contact emails count for matching."
        ),
    )

    include_unsubscribe_header = models.BooleanField(
        default=True,
        verbose_name="Include one-click unsubscribe",
        help_text="Add RFC 8058 List-Unsubscribe headers so recipients can unsubscribe directly from their email client.",
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
    error_message = models.TextField(
        blank=True,
        default="",
        help_text="Top-level error when the campaign fails before or during sending.",
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

        ex = (self.exclude_audience_type or "").strip()
        if ex:
            event_ex_types = ("event_registrants", "ticket_type", "checked_in", "not_checked_in")
            if ex in event_ex_types and not self.exclude_event_id:
                raise ValidationError({"exclude_event": "Select an event for this exclusion audience."})
