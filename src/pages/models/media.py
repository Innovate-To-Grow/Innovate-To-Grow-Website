"""
MediaAsset model for unified static file management.

Provides a centralized way to manage uploaded files (images, documents, etc.)
across development and production environments with different storage backends.
"""

import os
import uuid

from django.conf import settings
from django.db import models


def asset_upload_path(instance, filename):
    """
    Generate upload path for media assets.
    Uses UUID to ensure unique filenames and prevent collisions.

    Format: assets/{uuid}.{extension}
    """
    ext = os.path.splitext(filename)[1].lower()
    return f"assets/{instance.uuid}{ext}"


class MediaAsset(models.Model):
    """
    Unified media asset management.

    Stores metadata about uploaded files and provides consistent URL access
    regardless of the storage backend (local filesystem or cloud storage).
    """

    uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        help_text="Unique identifier for the asset.",
    )
    file = models.FileField(
        upload_to=asset_upload_path,
        help_text="The uploaded file.",
    )
    original_name = models.CharField(
        max_length=255,
        help_text="Original filename as uploaded by user.",
    )
    content_type = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="MIME type of the file (e.g., image/png).",
    )
    file_size = models.PositiveIntegerField(
        default=0,
        help_text="File size in bytes.",
    )
    alt_text = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Alternative text for images (accessibility).",
    )
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the file was uploaded.",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="uploaded_assets",
        help_text="User who uploaded the file.",
    )

    class Meta:
        ordering = ["-uploaded_at"]
        verbose_name = "Media Asset"
        verbose_name_plural = "Media Assets"

    def __str__(self):
        return f"{self.original_name} ({self.uuid})"

    @property
    def url(self):
        """Return the URL for this asset (works with any storage backend)."""
        return self.file.url if self.file else ""

    @property
    def extension(self):
        """Return the file extension (lowercase, without dot)."""
        if self.original_name:
            return os.path.splitext(self.original_name)[1].lower().lstrip(".")
        return ""

    @property
    def is_image(self):
        """Check if the asset is an image based on content type."""
        return self.content_type.startswith("image/")

    def save(self, *args, **kwargs):
        """Auto-populate file_size if not set."""
        if self.file and not self.file_size:
            try:
                self.file_size = self.file.size
            except Exception:
                pass
        super().save(*args, **kwargs)

