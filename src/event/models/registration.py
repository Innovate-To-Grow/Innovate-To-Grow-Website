import secrets

from django.conf import settings
from django.db import models

from core.models import ProjectControlModel


def generate_registration_ticket_code():
    return f"I2G-{secrets.token_hex(6).upper()}"


class EventRegistration(ProjectControlModel):
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="event_registrations",
    )
    event = models.ForeignKey(
        "event.Event",
        on_delete=models.CASCADE,
        related_name="registrations",
    )
    ticket = models.ForeignKey(
        "event.Ticket",
        on_delete=models.PROTECT,
        related_name="registrations",
    )
    ticket_code = models.CharField(
        max_length=24,
        unique=True,
        default=generate_registration_ticket_code,
        editable=False,
    )
    attendee_first_name = models.CharField(max_length=150, blank=True, default="")
    attendee_last_name = models.CharField(max_length=150, blank=True, default="")
    attendee_email = models.EmailField(blank=True, default="")
    attendee_organization = models.CharField(max_length=255, blank=True, default="")
    question_answers = models.JSONField(
        default=list,
        blank=True,
        help_text="Stored answers for event registration questions.",
    )
    ticket_email_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
    )
    ticket_email_error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["member", "event"],
                name="unique_event_registration_per_member",
            ),
        ]
        indexes = [
            models.Index(fields=["member", "created_at"]),
            models.Index(fields=["event", "created_at"]),
            models.Index(fields=["ticket_code"]),
        ]

    @property
    def attendee_name(self):
        return f"{self.attendee_first_name} {self.attendee_last_name}".strip()

    def __str__(self):
        return f"{self.event.name} - {self.attendee_name or self.member.get_primary_email()}"

    @property
    def barcode_payload(self):
        return f"I2G|EVENT|{self.event.slug}|{self.ticket_code}"

    def save(self, *args, **kwargs):
        if not self.attendee_first_name:
            self.attendee_first_name = self.member.first_name or self.member.username or self.member.get_primary_email()
        if not self.attendee_last_name:
            self.attendee_last_name = self.member.last_name or ""
        if not self.attendee_email:
            self.attendee_email = self.member.get_primary_email()
        if not self.attendee_organization:
            self.attendee_organization = getattr(self.member, "organization", "") or ""
        super().save(*args, **kwargs)
