"""Media models and helpers for CMS-managed assets."""

import os

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models

from core.models import ProjectControlModel

ALLOWED_ASSET_EXTENSIONS = ["png", "jpg", "jpeg", "gif", "webp", "svg", "pdf"]

# Magic-byte signatures for allowed file types
_MAGIC_SIGNATURES = [
    (b"\x89PNG", "png"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"%PDF", "pdf"),
]


def validate_asset_file_type(file):
    """Validate uploaded file by checking magic bytes against allowed types."""
    header = file.read(16)
    file.seek(0)

    for sig, _ in _MAGIC_SIGNATURES:
        if header.startswith(sig):
            return

    # RIFF....WEBP check
    if header[:4] == b"RIFF" and len(header) >= 12 and header[8:12] == b"WEBP":
        return

    # SVG files start with XML declaration or <svg tag
    if header.lstrip().startswith((b"<?xml", b"<svg")):
        return

    raise ValidationError("File type not allowed. Upload an image (PNG, JPEG, GIF, WebP, SVG) or PDF.")


def asset_upload_path(instance, filename):
    """Store uploaded CMS assets under a stable media prefix."""
    _, ext = os.path.splitext(filename or "")
    asset_id = getattr(instance, "id", None) or "unassigned"
    return os.path.join("cms", "assets", str(asset_id), f"asset{ext.lower()}")


class CMSAsset(ProjectControlModel):
    """Reusable uploaded asset for CMS editors."""

    name = models.CharField(max_length=200)
    file = models.FileField(
        upload_to=asset_upload_path,
        validators=[FileExtensionValidator(ALLOWED_ASSET_EXTENSIONS), validate_asset_file_type],
    )

    class Meta:
        db_table = "cms_cmsasset"
        ordering = ["name", "created_at"]
        verbose_name = "CMS Asset"
        verbose_name_plural = "CMS Assets"

    def __str__(self):
        return self.name

    @property
    def public_url(self):
        if not self.file:
            return ""
        return self.file.url
