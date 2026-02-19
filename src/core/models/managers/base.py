from django.db import models
from django.utils import timezone


class ProjectControlQuerySet(models.QuerySet):
    """QuerySet with soft delete support for bulk operations."""

    def delete(self):
        """Soft delete all records in the queryset."""
        return self.update(is_deleted=True, deleted_at=timezone.now())

    def hard_delete(self):
        """Permanently delete all records in the queryset."""
        return super().delete()

    def restore(self):
        """Restore all soft-deleted records in the queryset."""
        return self.update(is_deleted=False, deleted_at=None)


class ProjectControlManager(models.Manager):
    """Manager that filters out soft-deleted records by default."""

    def get_queryset(self):
        return ProjectControlQuerySet(self.model, using=self._db).filter(is_deleted=False)

    def deleted(self):
        """Return only soft-deleted records."""
        return ProjectControlQuerySet(self.model, using=self._db).filter(is_deleted=True)

    def with_deleted(self):
        """Return all records including soft-deleted ones."""
        return ProjectControlQuerySet(self.model, using=self._db)


class AllObjectsManager(models.Manager):
    """Manager that includes all records (including soft-deleted)."""

    def get_queryset(self):
        return ProjectControlQuerySet(self.model, using=self._db)
