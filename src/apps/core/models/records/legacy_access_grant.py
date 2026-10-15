from django.conf import settings
from django.db import models

from ..base import ProjectControlModel


class LegacyAccessGrant(ProjectControlModel):
    """One-time handoff from an I2G Admin session to the legacy viewer."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="legacy_access_grants",
    )
    code_digest = models.CharField(max_length=64, unique=True, editable=False)
    source_session_key = models.CharField(max_length=64, editable=False)
    source_session_expires_at = models.DateTimeField(editable=False)
    expires_at = models.DateTimeField(db_index=True, editable=False)
    consumed_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["expires_at", "consumed_at"],
                name="core_legacy_grant_exp_idx",
            )
        ]

    def __str__(self):
        state = "consumed" if self.consumed_at else "pending"
        return f"Legacy access for {self.user_id} ({state})"
