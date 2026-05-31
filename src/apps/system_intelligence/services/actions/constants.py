"""AI-action constants. The security-critical denylist constants are now owned by
the shared safe-ORM layer and re-exported here so the old import paths keep working.
"""

from apps.core.services.db_tools.helpers import MAX_ROWS
from apps.core.services.db_tools.safe_orm.constants import (
    DENIED_FIELD_NAMES,
    DENIED_MODEL_LABELS,
    DENIED_MODEL_NAME_PARTS,
    DENIED_READ_APP_LABELS,
    DENIED_WRITE_APP_LABELS,
    SAFE_LOOKUPS,
    SENSITIVE_FIELD_RE,
)

PREVIEW_TTL_SECONDS = 600
COMPARISON_MAX_BLOCKS = 8
COMPARISON_MAX_FIELDS = 8
COMPARISON_TEXT_LIMIT = 900
CMS_PAGE_FIELDS = {
    "slug",
    "route",
    "title",
    "meta_description",
    "page_css_class",
    "page_css",
    "status",
    "sort_order",
}
MAX_SAFE_ROWS = MAX_ROWS

__all__ = [
    "CMS_PAGE_FIELDS",
    "COMPARISON_MAX_BLOCKS",
    "COMPARISON_MAX_FIELDS",
    "COMPARISON_TEXT_LIMIT",
    "DENIED_FIELD_NAMES",
    "DENIED_MODEL_LABELS",
    "DENIED_MODEL_NAME_PARTS",
    "DENIED_READ_APP_LABELS",
    "DENIED_WRITE_APP_LABELS",
    "MAX_SAFE_ROWS",
    "PREVIEW_TTL_SECONDS",
    "SAFE_LOOKUPS",
    "SENSITIVE_FIELD_RE",
]
