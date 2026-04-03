import uuid

from django.db import models
from django.utils import timezone

from ..managers import AllObjectsManager, ProjectControlManager


class ProjectControlModel(models.Model):
    """
    Abstract base model combining UUID, timestamps, and soft delete.

    Features:
    - UUID as primary key
    - Automatic created_at and updated_at timestamps
    - Soft delete: delete() marks as deleted instead of removing

    Methods:
    - delete() / hard_delete() / restore() - Soft delete management

    Managers:
    - objects: Default manager, excludes soft-deleted records
    - all_objects: Includes all records (soft-deleted and active)
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = ProjectControlManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    # ========================
    # Soft Delete Methods
    # ========================

    def delete(self, using=None, keep_parents=False):
        """
        Soft delete: mark as deleted instead of removing from database.
        Override Django's default delete behavior.
        """
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(using=using, update_fields=["is_deleted", "deleted_at", "updated_at"])

    def hard_delete(self, using=None, keep_parents=False):
        """Permanently delete the record from the database."""
        return super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        """Restore a soft-deleted record."""
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])
