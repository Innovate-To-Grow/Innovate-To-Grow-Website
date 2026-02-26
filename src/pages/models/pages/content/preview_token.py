"""
PagePreviewToken model for shareable preview links.

Generates database-backed tokens that allow unauthenticated users
to preview unpublished pages via a shareable URL.
"""

import secrets
import uuid

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone


class PagePreviewToken(models.Model):
    """A shareable preview token for an unpublished page or homepage."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    token = models.CharField(max_length=64, unique=True, db_index=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    content_object = GenericForeignKey("content_type", "object_id")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="preview_tokens",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(help_text="When this preview link expires.")
    is_active = models.BooleanField(default=True)
    note = models.CharField(max_length=255, blank=True, default="", help_text="Optional note about this preview link.")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Page Preview Token"
        verbose_name_plural = "Page Preview Tokens"

    def __str__(self):
        return f"Preview token for {self.content_object} (expires {self.expires_at})"

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)

    @property
    def is_valid(self):
        """Check if the token is active and not expired."""
        return self.is_active and self.expires_at > timezone.now()

    def revoke(self):
        """Deactivate this token."""
        self.is_active = False
        self.save(update_fields=["is_active"])
