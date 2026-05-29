"""
Shared abstract base models.

NOTE: Most domain models in this project inherit from
``apps.core.models.ProjectControlModel``, which already provides UUID primary
keys, ``created_at``/``updated_at`` timestamps, soft delete, and version
tracking. ``TimeStampedModel`` here is the lighter, framework-standard base
offered for new models that only need timestamps and do not want the full
ProjectControlModel feature set. It is abstract, so it adds no database table
and no migration.
"""

from django.db import models


class TimeStampedModel(models.Model):
    """Abstract base adding self-managed ``created_at`` / ``updated_at`` fields."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        get_latest_by = "created_at"
