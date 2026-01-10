"""Shared core models."""

from .base import (
    ActiveModel,
    AuthoredModel,
    ModelVersion,
    OrderedModel,
    ProjectControlManager,
    ProjectControlModel,
    ProjectControlQuerySet,
    # Legacy aliases for backward compatibility
    SoftDeleteManager,
    SoftDeleteModel,
    TimeStampedModel,
    UUIDModel,
)

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
