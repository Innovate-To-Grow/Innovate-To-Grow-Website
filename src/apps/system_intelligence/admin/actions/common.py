"""What every action admin view shares: its logger, the user-facing errors, and the actions service."""

import logging

from apps.system_intelligence.services import actions as system_intelligence_actions

# The package's logger, so its records keep the name they always had.
logger = logging.getLogger("apps.system_intelligence.admin.actions")

GENERIC_ACTION_ERROR = "Could not process this action request."
GENERIC_PERMISSION_ERROR = "Action request not found."
GENERIC_VALIDATION_ERROR = "Validation failed for the proposed change."

__all__ = [
    "GENERIC_ACTION_ERROR",
    "GENERIC_PERMISSION_ERROR",
    "GENERIC_VALIDATION_ERROR",
    "logger",
    "system_intelligence_actions",
]
