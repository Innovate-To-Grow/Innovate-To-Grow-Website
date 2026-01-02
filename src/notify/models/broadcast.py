"""
Broadcast message model for pushing notifications to subscribers.
"""

from django.db import models

from core.models.base import AuthoredModel, TimeStampedModel
from .verification import VerificationRequest


class BroadcastMessage(TimeStampedModel, AuthoredModel):
    """
    Stores email/SMS campaign content that can be sent to subscribed contacts.
    """

    STATUS_DRAFT = "draft"
    STATUS_SENDING = "sending"
    STATUS_SENT = "sent"
    STATUS_PARTIAL = "partial"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_SENDING, "Sending"),
        (STATUS_SENT, "Sent"),
        (STATUS_PARTIAL, "Partial"),
        (STATUS_FAILED, "Failed"),
    ]

    name = models.CharField(
        max_length=128,
        help_text="Internal name so admins can identify this broadcast.",
    )
    channel = models.CharField(
        max_length=10,
        choices=VerificationRequest.CHANNEL_CHOICES,
        help_text="Delivery channel for this broadcast.",
    )
    scope = models.CharField(
        max_length=64,
        default="general",
        help_text="Audience scope/list that should receive this broadcast.",
    )
    subject = models.CharField(
        max_length=255,
        blank=True,
        help_text="Subject line for email broadcasts.",
    )
    message = models.TextField(
        help_text="Body of the broadcast message (HTML allowed for email).",
    )
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        help_text="Lifecycle status of this broadcast.",
    )
    total_recipients = models.PositiveIntegerField(
        default=0,
        help_text="Total subscribers targeted when the broadcast was sent.",
    )
    sent_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of recipients successfully sent.",
    )
    failed_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of recipients that failed to send.",
    )
    last_error = models.TextField(
        blank=True,
        help_text="Last error captured while sending.",
    )
    sent_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Timestamp when sending completed.",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["channel"], name="notify_broadcast_channel_idx"),
            models.Index(fields=["status"], name="notify_broadcast_status_idx"),
            models.Index(fields=["scope"], name="notify_broadcast_scope_idx"),
        ]
        verbose_name = "Broadcast Message"
        verbose_name_plural = "Broadcast Messages"

    def __str__(self) -> str:
        return f"{self.name} ({self.channel})"

    @property
    def is_sendable(self) -> bool:
        """
        Broadcast can only be sent when in draft/failed/partial state.
        """

        return self.status in {
            self.STATUS_DRAFT,
            self.STATUS_FAILED,
            self.STATUS_PARTIAL,
        }

