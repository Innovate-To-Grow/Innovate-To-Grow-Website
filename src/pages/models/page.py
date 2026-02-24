"""
Compatibility shim for imports that reference `pages.models.page`.

The actual implementations live in the `pages.models.pages` subpackage.
"""

from .pages.content.page import Page  # noqa: F401
from .pages.shared.validators import validate_nested_slug  # noqa: F401

__all__ = ["Page", "validate_nested_slug"]
