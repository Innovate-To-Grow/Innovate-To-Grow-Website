"""
Compatibility shim for legacy migration imports.

Existing migrations reference `pages.models.page` for the Page model and
the `validate_nested_slug` validator. The actual implementations live in
`pages.models.pages.content.page` and `pages.models.pages.shared.validators`. This module
simply re-exports them so migrations continue to work without modification.
"""

from .pages.component.page_component import PageComponent  # noqa: F401
from .pages.content.page import Page  # noqa: F401
from .pages.shared.validators import validate_nested_slug  # noqa: F401

__all__ = ["Page", "PageComponent", "validate_nested_slug"]
