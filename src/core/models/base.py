"""Legacy import path for core models."""

from .legacy import SoftDeleteManager, SoftDeleteModel, TimeStampedModel, UUIDModel
from .managers import AllObjectsManager, ProjectControlManager, ProjectControlQuerySet
from .mixins import ActiveModel, AuthoredModel, OrderedModel
from .versioning import ModelVersion, ProjectControlModel

__all__ = [
    "ActiveModel",
    "AllObjectsManager",
    "AuthoredModel",
    "ModelVersion",
    "OrderedModel",
    "ProjectControlManager",
    "ProjectControlModel",
    "ProjectControlQuerySet",
    "SoftDeleteManager",
    "SoftDeleteModel",
    "TimeStampedModel",
    "UUIDModel",
]
