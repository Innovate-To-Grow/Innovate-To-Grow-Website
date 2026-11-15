from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import ProjectControlModel
from apps.mail.models.email.campaign_options import STATUS_CHOICES

from .campaign_options import (
    E164_RE,
    LINKS_OFF_MESSAGE,
    SMS_AUDIENCE_CHOICES,
    SMS_EXCLUDE_AUDIENCE_CHOICES,
    SMS_LINK_PLACEHOLDERS,
    SMS_PHONE_POLICY_CHOICES,
    parse_manual_sms_phones,
)


class SmsCampaign(ProjectControlModel):
    name = models.CharField(max_length=200, blank=True, default="")
    message = models.TextField(
        verbose_name="SMS Message",
        help_text=(
            "Plain text message. Supports {{first_name}}, {{last_name}} and {{full_name}}; with links in SMS allowed "
            "(Mail → SMS Settings) also {{login_link}}, {{ticket_link}} and {{event_link}}. The opt-out footer is "
            "added when the message does not say STOP."
        ),
    )
    login_redirect_path = models.CharField(
        max_length=200,
        default="/account",
        verbose_name="Sign-in destination",
        help_text="Where {{login_link}} lands after signing in.",
    )
    link_validity_days = models.PositiveSmallIntegerField(
        default=3,
        verbose_name="Link validity (days)",
        help_text="How long the links in this campaign's texts work after it is sent.",
    )
    phone_policy = models.CharField(
        max_length=24,
        choices=SMS_PHONE_POLICY_CHOICES,
        default="verified_opt_in",
        verbose_name="Phone eligibility",
        help_text=(
            "Verified opt-ins uses verified subscribed contact phones. "
            "Any verified also allows verified event registration phones."
        ),
    )

    audience_type = models.CharField(max_length=32, choices=SMS_AUDIENCE_CHOICES, default="subscribers")
    event = models.ForeignKey(
        "event.Event",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sms_campaigns",
        help_text="Required for event-based SMS audiences; also the event {{event_link}} and {{ticket_link}} open.",
    )
    ticket_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Ticket UUID when audience is 'Event Ticket Type'.",
    )
    selected_members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="selected_sms_campaigns",
        help_text="Pick members when audience is 'Selected Members'.",
    )
    manual_phones = models.TextField(
        blank=True,
        default="",
        help_text="One E.164 phone number per line, for example +12095551234.",
    )

    exclude_audience_type = models.CharField(
        max_length=32,
        choices=SMS_EXCLUDE_AUDIENCE_CHOICES,
        blank=True,
        default="",
        verbose_name="Exclude audience",
        help_text="Remove matching phone numbers from the final recipient list.",
    )
    exclude_event = models.ForeignKey(
        "event.Event",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Event used to build the SMS exclusion list for event-based exclusions.",
    )
    exclude_ticket_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Ticket UUID when exclude audience is 'Event Ticket Type'.",
    )
    exclude_members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="+",
        help_text='When exclude audience is "Selected Members", pick members here.',
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
        help_text="Top-level error when the SMS campaign fails before or during sending.",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Broadcast SMS"
        verbose_name_plural = "Broadcast SMS"

    def __str__(self):
        label = self.name or self.message[:60] or "Untitled"
        return f"{label} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        if not self.name:
            self.name = self.message[:200] if self.message else "Untitled"
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        event_required_types = ("event_registrants", "ticket_type", "checked_in", "not_checked_in")
        if self.audience_type in event_required_types and not self.event_id:
            raise ValidationError(
                {"event": f"An event must be selected for the '{self.get_audience_type_display()}' audience."}
            )
        if self.audience_type == "ticket_type" and not self.ticket_id.strip():
            raise ValidationError({"ticket_id": "A ticket type must be selected."})
        if self.audience_type == "manual":
            self._clean_manual_phones()
        self._clean_links()

        ex = (self.exclude_audience_type or "").strip()
        if ex:
            if ex in event_required_types and not self.exclude_event_id:
                raise ValidationError({"exclude_event": "Select an event for this exclusion audience."})
            if ex == "ticket_type" and not self.exclude_ticket_id.strip():
                raise ValidationError({"exclude_ticket_id": "A ticket type must be selected for ticket exclusion."})

    def _clean_links(self):
        """Link placeholders only while links in SMS are allowed; ``{{event_link}}`` needs an event."""
        from apps.mail.redirects import is_strict_internal_path
        from apps.mail.services.campaign.personalize import uses_placeholder

        from .config import SmsConfig

        used = [name for name in SMS_LINK_PLACEHOLDERS if uses_placeholder(name, self.message)]
        if used and not SmsConfig.load().links_enabled:
            raise ValidationError({"message": LINKS_OFF_MESSAGE})
        if "event_link" in used and not self.event_id:
            raise ValidationError({"event": "Choose the event {{event_link}} opens."})
        maximum = settings.SMS_POLICY["link_max_validity_days"]
        if not 1 <= (self.link_validity_days or 0) <= maximum:
            raise ValidationError({"link_validity_days": f"Choose 1 to {maximum} days."})
        if not is_strict_internal_path(self.login_redirect_path):
            raise ValidationError({"login_redirect_path": "Please select a valid internal destination."})

    def _clean_manual_phones(self):
        phones = parse_manual_sms_phones(self.manual_phones)
        if not phones:
            raise ValidationError({"manual_phones": "Please enter at least one E.164 phone number."})
        invalid = [phone for phone in phones if not E164_RE.match(phone)]
        if invalid:
            raise ValidationError({"manual_phones": f"Invalid E.164 phone number: {invalid[0]}"})
