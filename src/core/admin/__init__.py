"""
Core admin utilities and base classes.

Provides shared functionality for admin interfaces across all apps.
"""

from .base import BaseModelAdmin, ReadOnlyModelAdmin
from .log_entry import LogEntryAdmin  # noqa: F401 - register admin
from .maintenance import SiteMaintenanceControlAdmin  # noqa: F401 - register admin
from .mixins import (
    ExportMixin,
    ImportExportMixin,
    SoftDeleteAdminMixin,
    TimestampedAdminMixin,
)
from .service_credentials import (  # noqa: F401 - register admin
    EmailServiceConfigAdmin,
    GoogleCredentialConfigAdmin,
    SMSServiceConfigAdmin,
)
from .utils import admin_url, format_duration, format_file_size, format_json, get_field_value, truncate_text

__all__ = [
    # Base classes
    "BaseModelAdmin",
    "ReadOnlyModelAdmin",
    # Mixins
    "SoftDeleteAdminMixin",
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
