import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import ProjectControlModel
from apps.mail.models.campaign import STATUS_CHOICES

SMS_AUDIENCE_CHOICES = [
    ("subscribers", "SMS Subscribers"),
    ("event_registrants", "Event Registrants"),
    ("ticket_type", "Event Ticket Type"),
    ("checked_in", "Checked-In Attendees"),
    ("not_checked_in", "No-Shows (Not Checked In)"),
    ("all_members", "All Active Members"),
    ("staff", "Staff Members"),
    ("selected_members", "Selected Members"),
    ("manual", "Manual Phones"),
]

SMS_EXCLUDE_AUDIENCE_CHOICES = [
    ("", "No exclusion"),
    ("subscribers", "SMS Subscribers"),
    ("event_registrants", "Event Registrants"),
    ("ticket_type", "Event Ticket Type"),
    ("checked_in", "Checked-In Attendees"),
    ("not_checked_in", "No-Shows (Not Checked In)"),
    ("all_members", "All Active Members"),
    ("staff", "Staff Members"),
    ("selected_members", "Selected Members"),
]

SMS_PHONE_POLICY_CHOICES = [
    ("verified_opt_in", "Verified opt-ins"),
    ("any_verified", "Any verified phone"),
]

SMS_LOG_STATUS_CHOICES = [
    ("pending", "Pending"),
    ("sent", "Sent"),
    ("failed", "Failed"),
]

E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")


class SmsCampaign(ProjectControlModel):
    name = models.CharField(max_length=200, blank=True, default="")
    message = models.TextField(
        verbose_name="SMS Message",
        help_text=(
            "Plain text message. Supports {{first_name}}, {{last_name}}, and {{full_name}}. "
            "Opt-out wording is not added automatically."
        ),
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
        help_text="Required for event-based SMS audiences.",
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

        ex = (self.exclude_audience_type or "").strip()
        if ex:
            if ex in event_required_types and not self.exclude_event_id:
                raise ValidationError({"exclude_event": "Select an event for this exclusion audience."})
            if ex == "ticket_type" and not self.exclude_ticket_id.strip():
                raise ValidationError({"exclude_ticket_id": "A ticket type must be selected for ticket exclusion."})

    def _clean_manual_phones(self):
        phones = parse_manual_sms_phones(self.manual_phones)
        if not phones:
            raise ValidationError({"manual_phones": "Please enter at least one E.164 phone number."})
        invalid = [phone for phone in phones if not E164_RE.match(phone)]
        if invalid:
            raise ValidationError({"manual_phones": f"Invalid E.164 phone number: {invalid[0]}"})


class SmsRecipientLog(ProjectControlModel):
    campaign = models.ForeignKey(
        "mail.SmsCampaign",
        on_delete=models.CASCADE,
        related_name="recipient_logs",
    )
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    phone_number = models.CharField(max_length=20)
    recipient_name = models.CharField(max_length=300, blank=True, default="")
    status = models.CharField(max_length=16, choices=SMS_LOG_STATUS_CHOICES, default="pending")
    provider = models.CharField(max_length=16, blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    sns_message_id = models.CharField(max_length=256, blank=True, default="", db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "SMS Recipient Log"
        verbose_name_plural = "SMS Recipient Logs"
        constraints = [
            models.UniqueConstraint(fields=["campaign", "phone_number"], name="unique_sms_campaign_recipient"),
        ]

    def __str__(self):
        return f"{self.phone_number} - {self.get_status_display()}"


def parse_manual_sms_phones(body: str) -> list[str]:
    phones = []
    seen = set()
    for line in (body or "").strip().splitlines():
        phone = line.strip()
        if not phone or phone in seen:
            continue
        seen.add(phone)
        phones.append(phone)
    return phones
