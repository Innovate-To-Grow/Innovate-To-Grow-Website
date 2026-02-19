import uuid

from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone

from ..managers import AllObjectsManager, ProjectControlManager
from ..versioning import ModelVersion


class ProjectControlModel(models.Model):
    """
    Abstract base model combining UUID, timestamps, soft delete, and versioning.

    Features:
    - UUID as primary key
    - Automatic created_at and updated_at timestamps
    - Soft delete: delete() marks as deleted instead of removing
    - Version control: save snapshots and rollback to previous versions

    Methods:
    - delete() / hard_delete() / restore() - Soft delete management
    - save_version(comment, user) - Save current state as a new version
    - get_versions() - Get all version history
    - rollback(version_number, user) - Restore to a specific version
    - get_version(version_number) - Get a specific version's data

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
    version = models.PositiveIntegerField(default=0, editable=False)

    # Generic relation to versions
    versions = GenericRelation(
        ModelVersion,
        content_type_field="content_type",
        object_id_field="object_id",
    )

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

    # ========================
    # Version Control Methods
    # ========================

    def _get_version_fields(self):
        """Get fields to include in version snapshot (exclude control fields)."""
        exclude_fields = {
            "id",
            "created_at",
            "updated_at",
            "is_deleted",
            "deleted_at",
            "version",
            "versions",
        }
        return [f for f in self._meta.get_fields() if f.name not in exclude_fields and f.concrete]

    def _serialize_for_version(self):
        """Serialize model data for version storage."""
        data = {}
        for field in self._get_version_fields():
            value = getattr(self, field.name)
            # Handle special field types
            if isinstance(value, uuid.UUID):
                value = str(value)
            elif hasattr(value, "pk"):  # ForeignKey
                value = str(value.pk) if value.pk else None
            data[field.name] = value
        return data

    def _deserialize_from_version(self, data):
        """Apply version data to the model instance."""
        for field in self._get_version_fields():
            if field.name in data:
                value = data[field.name]
                # Handle ForeignKey fields
                if field.is_relation and field.many_to_one:
                    if value:
                        try:
                            related_model = field.related_model
                            value = related_model.objects.get(pk=value)
                        except related_model.DoesNotExist:
                            value = None
                    else:
                        value = None
                setattr(self, field.name, value)

    def save_version(self, comment="", user=None):
        """
        Save current state as a new version.

        Args:
            comment: Optional description of this version
            user: User who created this version

        Returns:
            ModelVersion: The created version instance
        """
        self.version += 1
        self.save(update_fields=["version", "updated_at"])

        content_type = ContentType.objects.get_for_model(self)
        version = ModelVersion.objects.create(
            content_type=content_type,
            object_id=self.pk,
            version_number=self.version,
            data=self._serialize_for_version(),
            comment=comment,
            created_by=user,
        )
        return version

    def get_versions(self):
        """
        Get all versions for this instance.

        Returns:
            QuerySet: All ModelVersion objects for this instance, newest first
        """
        return self.versions.all().order_by("-version_number")

    def get_version(self, version_number):
        """
        Get a specific version's data.

        Args:
            version_number: The version number to retrieve

        Returns:
            dict: The version data, or None if not found
        """
        try:
            version = self.versions.get(version_number=version_number)
            return version.data
        except ModelVersion.DoesNotExist:
            return None

    def rollback(self, version_number, user=None, save_current=True):
        """
        Rollback to a specific version.

        Args:
            version_number: The version number to rollback to
            user: User performing the rollback
            save_current: If True, save current state as a new version before rollback

        Returns:
            ModelVersion: The newly created version after rollback

        Raises:
            ValueError: If the specified version doesn't exist
        """
        try:
            target_version = self.versions.get(version_number=version_number)
        except ModelVersion.DoesNotExist:
            raise ValueError(f"Version {version_number} does not exist")

        # Optionally save current state before rollback
        if save_current:
            self.save_version(
                comment=f"Auto-saved before rollback to v{version_number}",
                user=user,
            )

        # Apply the target version's data
        self._deserialize_from_version(target_version.data)

        # Save as new version
        return self.save_version(
            comment=f"Rolled back to v{version_number}",
            user=user,
        )

    def get_version_diff(self, version_a, version_b):
        """
        Compare two versions and return the differences.

        Args:
            version_a: First version number
            version_b: Second version number

        Returns:
            dict: Dictionary with changed fields {field: (old_value, new_value)}
        """
        data_a = self.get_version(version_a)
        data_b = self.get_version(version_b)

        if data_a is None or data_b is None:
            raise ValueError("One or both versions do not exist")

        diff = {}
        all_keys = set(data_a.keys()) | set(data_b.keys())
        for key in all_keys:
            val_a = data_a.get(key)
            val_b = data_b.get(key)
            if val_a != val_b:
                diff[key] = (val_a, val_b)
        return diff
