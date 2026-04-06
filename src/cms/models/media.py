"""Media models and helpers for CMS-managed assets."""

import os

from django.db import models

from core.models import ProjectControlModel


def asset_upload_path(instance, filename):
    """Store uploaded CMS assets under a stable media prefix."""
    _, ext = os.path.splitext(filename or "")
    asset_id = getattr(instance, "id", None) or "unassigned"
    return os.path.join("cms", "assets", str(asset_id), f"asset{ext.lower()}")


class CMSAsset(ProjectControlModel):
    """Reusable uploaded asset for CMS editors."""

    name = models.CharField(max_length=200)
    file = models.FileField(upload_to=asset_upload_path)

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
