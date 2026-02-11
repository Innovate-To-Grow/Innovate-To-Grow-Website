"""
Event registration domain models.
"""

from django.db import models

from core.models.base.control import ProjectControlModel


class EventTicketOption(ProjectControlModel):
    """Ticket options configured per event (e.g. Attendee, Judge)."""

    event = models.ForeignKey(
        "events.Event",
        on_delete=models.CASCADE,
        related_name="ticket_options",
    )
    label = models.CharField(max_length=255)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "created_at", "id"]
        unique_together = [["event", "label"]]
        indexes = [
            models.Index(fields=["event", "order"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return f"{self.event.event_name} - {self.label}"


class EventQuestion(ProjectControlModel):
    """Custom questions asked during event registration."""

    event = models.ForeignKey(
        "events.Event",
        on_delete=models.CASCADE,
        related_name="questions",
    )
    prompt = models.CharField(max_length=500)
    order = models.PositiveIntegerField(default=0)
    required = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "created_at", "id"]
        unique_together = [["event", "prompt"]]
        indexes = [
            models.Index(fields=["event", "order"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return f"{self.event.event_name} - Q{self.order + 1}: {self.prompt[:60]}"


class EventRegistration(ProjectControlModel):
    """
    Registration record for one member on one event.
    """

    STATUS_PENDING = "pending"
    STATUS_OTP_PENDING = "otp_pending"
    STATUS_VERIFIED = "verified"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_OTP_PENDING, "OTP Pending"),
        (STATUS_VERIFIED, "Verified"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    event = models.ForeignKey(
        "events.Event",
        on_delete=models.CASCADE,
        related_name="registrations",
        help_text="The event this registration is for",
        verbose_name="Event",
    )

    member = models.ForeignKey(
        "authn.Member",
        on_delete=models.CASCADE,
        related_name="event_registrations",
        help_text="The member who registered",
        verbose_name="Member",
    )

    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_PENDING)

    ticket_option = models.ForeignKey(
        "events.EventTicketOption",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registrations",
    )
    ticket_label = models.CharField(max_length=255, blank=True, default="")
    source_email = models.EmailField(blank=True, default="")

    primary_email_subscribed = models.BooleanField(default=False)
    secondary_email_subscribed = models.BooleanField(default=False)
    phone_subscribed = models.BooleanField(default=False)
    phone_verified = models.BooleanField(default=False)

    registration_token = models.CharField(max_length=64, blank=True, null=True, unique=True, db_index=True)
    otp_target_phone = models.CharField(max_length=20, blank=True, default="")
    otp_requested_at = models.DateTimeField(null=True, blank=True)
    otp_verified_at = models.DateTimeField(null=True, blank=True)

    submitted_at = models.DateTimeField(null=True, blank=True)
    profile_snapshot = models.JSONField(default=dict, blank=True)

    registered_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the member registered for this event",
        verbose_name="Registered At",
    )

    class Meta:
        verbose_name = "Event Registration"
        verbose_name_plural = "Event Registrations"
        ordering = ["-registered_at"]
        unique_together = [["event", "member"]]
        indexes = [
            models.Index(fields=["event"]),
            models.Index(fields=["member"]),
            models.Index(fields=["registered_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.member.get_full_name() or self.member.username} - {self.event.event_name}"


class EventRegistrationAnswer(ProjectControlModel):
    """Answer rows for event registration questions."""

    registration = models.ForeignKey(
        "events.EventRegistration",
        on_delete=models.CASCADE,
        related_name="answers",
    )
    question = models.ForeignKey(
        "events.EventQuestion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="answers",
    )
    question_prompt = models.CharField(max_length=500)
    answer_text = models.TextField(blank=True, default="")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "created_at", "id"]
        unique_together = [["registration", "question_prompt"]]
        indexes = [
            models.Index(fields=["registration", "order"]),
        ]

    def __str__(self):
        return f"{self.registration_id} - {self.question_prompt[:60]}"
