from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import ProjectControlModel

# The two member-wide audiences differ only in the subscribe flag (services/audience/resolvers.py), so their labels
# say so; which of a member's addresses are used is the "Send to" field's business, explained in the help texts.
from .campaign_options import (
    _ALL_AUDIENCE_LABELS,
    ALL_AUDIENCE_CHOICES,
    AUDIENCE_HELP_TEXT,
    EXCLUDE_AUDIENCE_CHOICES,
    MEMBER_EMAIL_CHOICES,
    STATUS_CHOICES,
)
from .campaign_safety import EmailCampaignSafetyMixin, connect_retry_audience_guards, retry_constraints


class EmailCampaign(EmailCampaignSafetyMixin, ProjectControlModel):
    name = models.CharField(max_length=200, blank=True, default="")
    subject = models.CharField(max_length=998)
    body = models.TextField(verbose_name="Email Content", blank=True, default="")
    login_redirect_path = models.CharField(
        max_length=200,
        default="/account",
        verbose_name="Post-login destination",
        help_text="Internal site page where recipients land after one-click login.",
    )
    login_link_validity_days = models.PositiveSmallIntegerField(
        default=7,
        validators=[MinValueValidator(1), MaxValueValidator(90)],
        verbose_name="Login link validity (days)",
        help_text="How long each recipient's {{login_link}} stays valid after this campaign is sent (1-90 days).",
    )
    login_link_reusable = models.BooleanField(
        default=False,
        verbose_name="Reusable login links",
        help_text=(
            "Allow recipients to sign in with their {{login_link}} repeatedly until it expires. "
            "Off: each link works exactly once. This is checked at login time, so unticking it "
            "later immediately blocks further reuse of links from this campaign."
        ),
    )

    audience_type = models.CharField(
        max_length=32, choices=ALL_AUDIENCE_CHOICES, default="subscribers", help_text=AUDIENCE_HELP_TEXT
    )
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
            "For member-based audiences (All subscribers, All active members, Staff Members, Selected Members): "
            "send only to each person's primary contact email, or to every saved contact email "
            "(primary, secondary, and other). For All subscribers, only the addresses that are themselves "
            "subscribed receive the email, so with primary only a member whose primary address is unsubscribed "
            "gets nothing even when another of their addresses is subscribed. Event-based audiences (registrants, "
            "ticket, checked-in, no-shows) use the registration's attendee email when set, otherwise the member's "
            "primary email."
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
        help_text=(
            "One email per line. Used when audience is 'Manual Emails'. An address that is an active member's "
            "contact email gets that member's name and personal {{login_link}}; any other address gets empty name "
            "tags and a link to the sign-in page for {{login_link}}."
        ),
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
        constraints = retry_constraints()

    def get_audience_type_display(self):
        return _ALL_AUDIENCE_LABELS.get(self.audience_type, self.audience_type)

    def __str__(self):
        label = self.name or self.subject[:60] or "Untitled"
        return f"{label} ({self.get_status_display()})"


connect_retry_audience_guards(EmailCampaign)
