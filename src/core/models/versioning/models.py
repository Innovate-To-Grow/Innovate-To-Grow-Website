import uuid

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models


class ModelVersion(models.Model):
    """Stores version history for any model that inherits ProjectControlModel."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Generic foreign key to link to any model
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField(db_index=True)
    content_object = GenericForeignKey("content_type", "object_id")

    # Version info
    version_number = models.PositiveIntegerField(db_index=True)
    data = models.JSONField(encoder=DjangoJSONEncoder)
    comment = models.TextField(blank=True, default="")

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="model_versions_created",
    )

    class Meta:
        ordering = ["-version_number"]
        unique_together = [["content_type", "object_id", "version_number"]]
        indexes = [
            models.Index(fields=["content_type", "object_id", "-version_number"]),
        ]

    def __str__(self):
        return f"{self.content_type} #{self.object_id} v{self.version_number}"
