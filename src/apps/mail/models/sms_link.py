"""SMS short links (``/l/<token>``) and the record of each ticket text.

``SmsLinkToken`` is what ``{{login_link}}``, ``{{ticket_link}}`` and ``{{event_link}}`` become in a text: a short,
random, expiring token with one purpose. The URL carries nothing but the token (no member, phone or event), and the
table keeps only its SHA-256 digest. Two kinds:

- **personal** (``member`` set): signs that member in once and lands on ``redirect_path``; issued per recipient,
  only when personal sign-in links are on, never to staff, and only to a phone that is the member's own verified
  account phone (``phone_digest``): opening it checks again that the member still has that phone;
- **shared** (no member): one per campaign and purpose, sends everyone to ``redirect_path`` (the sign-in page with a
  return path, or the event page). It is no credential, so its plain token is kept to put it in every recipient's text.

``TicketSms`` records the ticket text of one registration (phone-only registrants, Mail → SMS Settings).
"""

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.models import ProjectControlModel


class SmsLinkToken(ProjectControlModel):
    class Purpose(models.TextChoices):
        LOGIN = "login", "Sign in ({{login_link}})"
        TICKET = "ticket", "Ticket ({{ticket_link}})"
        EVENT = "event", "Event page ({{event_link}})"

    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    public_token = models.CharField(max_length=64, blank=True, default="", editable=False)
    purpose = models.CharField(max_length=16, choices=Purpose.choices)
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    campaign = models.ForeignKey(
        "mail.SmsCampaign", null=True, blank=True, on_delete=models.CASCADE, related_name="links"
    )
    registration = models.ForeignKey(
        "event.EventRegistration", null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    redirect_path = models.CharField(max_length=200, editable=False)
    # SHA-256 of the E.164 number a personal link was texted to (that member's own verified phone); empty otherwise.
    phone_digest = models.CharField(max_length=64, blank=True, default="", editable=False)
    expires_at = models.DateTimeField(db_index=True)
    first_used_at = models.DateTimeField(null=True, blank=True)
    use_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "SMS link"
        verbose_name_plural = "SMS links"
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "purpose"],
                condition=Q(member__isnull=True, campaign__isnull=False),
                name="mail_one_shared_sms_link_per_purpose",
            ),
        ]

    def __str__(self):
        kind = "personal" if self.is_personal else "shared"
        return f"{self.get_purpose_display()} ({kind})"

    @property
    def is_personal(self) -> bool:
        return self.member_id is not None

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at


class TicketSms(ProjectControlModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Waiting to send"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        UNCERTAIN = "uncertain", "Uncertain delivery"
        SKIPPED = "skipped", "Not sent"
        OPTED_OUT = "opted_out", "Opted out"

    registration = models.OneToOneField("event.EventRegistration", on_delete=models.CASCADE, related_name="+")
    phone_number = models.CharField(max_length=20)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    error_message = models.CharField(max_length=300, blank=True, default="")
    message_id = models.CharField(max_length=256, blank=True, default="")
    available_at = models.DateTimeField(null=True, blank=True, help_text="Not sent before this (quiet hours).")
    sent_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Ticket SMS"
        verbose_name_plural = "Ticket SMS"

    def __str__(self):
        return f"Ticket SMS to {self.phone_number} ({self.get_status_display()})"
