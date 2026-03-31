"""
Core admin utilities and base classes.

Provides shared functionality for admin interfaces across all apps.
"""

from .base import BaseModelAdmin, ReadOnlyModelAdmin
from .maintenance import SiteMaintenanceControlAdmin  # noqa: F401 - register admin
from .mixins import (
    ExportMixin,
    ImportExportMixin,
    SoftDeleteAdminMixin,
    TimestampedAdminMixin,
    VersionControlAdminMixin,
)
from .service_credentials import EmailServiceConfigAdmin, SMSServiceConfigAdmin  # noqa: F401 - register admin
from .utils import admin_url, format_duration, format_file_size, format_json, get_field_value, truncate_text
from .version_history import ModelVersionAdmin  # noqa: F401 - register admin

__all__ = [
    # Base classes
    "BaseModelAdmin",
    "ReadOnlyModelAdmin",
    "ModelVersionAdmin",
    # Mixins
    "SoftDeleteAdminMixin",
    "VersionControlAdminMixin",
    "TimestampedAdminMixin",
    "ImportExportMixin",
    "ExportMixin",
    # Utilities
    "admin_url",
    "truncate_text",
    "format_json",
    "get_field_value",
    "format_file_size",
    "format_duration",
]
