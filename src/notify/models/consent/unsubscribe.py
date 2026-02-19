"""
Models that track unsubscribe/opt-out requests.
"""

import uuid

from django.db import models

from core.models import ProjectControlModel

from ..delivery import VerificationRequest


def default_metadata() -> dict:
    """
    Provide a new dict for JSONField defaults.
    """

    return {}


class Unsubscribe(ProjectControlModel):
    """
    Stores unsubscribe requests for email/SMS channels.
    """

    channel = models.CharField(
        max_length=10,
        choices=VerificationRequest.CHANNEL_CHOICES,
        help_text="Channel the recipient opted out from.",
    )
    target = models.CharField(
        max_length=255,
        help_text="Email address or phone number that opted out.",
    )
    scope = models.CharField(
        max_length=64,
        default="general",
        help_text="Logical scope/list this unsubscribe applies to.",
    )
    reason = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional reason provided for the unsubscribe.",
    )
    metadata = models.JSONField(
        default=default_metadata,
        blank=True,
        help_text="Optional structured details captured during unsubscribe.",
    )
    token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        help_text="Token that can be used to confirm or revert the unsubscribe.",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["channel", "target"],
                name="notify_unsub_target_idx",
            ),
            models.Index(
                fields=["token"],
                name="notify_unsub_token_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["channel", "target", "scope"],
                name="notify_unsub_unique_target_scope",
            ),
        ]
        verbose_name = "Unsubscribe"
        verbose_name_plural = "Unsubscribes"

    def __str__(self) -> str:
        return f"{self.channel}:{self.target} ({self.scope})"
