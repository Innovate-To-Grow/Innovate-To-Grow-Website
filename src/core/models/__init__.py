"""Shared core models."""

from .legacy import SoftDeleteManager, SoftDeleteModel, TimeStampedModel, UUIDModel
from .managers import ProjectControlManager, ProjectControlQuerySet
from .mixins import ActiveModel, AuthoredModel, OrderedModel
from .versioning import ModelVersion, ProjectControlModel

__all__ = [
    "ActiveModel",
    "AuthoredModel",
    "ModelVersion",
    "OrderedModel",
    "ProjectControlManager",
    "ProjectControlModel",
    "ProjectControlQuerySet",
    # Legacy aliases
    "SoftDeleteManager",
    "SoftDeleteModel",
    "TimeStampedModel",
    "UUIDModel",
]
