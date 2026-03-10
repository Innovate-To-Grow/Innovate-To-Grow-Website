"""
Pages app models export.

Aggregates commonly used models so callers can import from `pages.models`.
"""

from .pages import (
    FooterContent,
    Menu,
)

__all__ = [
    # Layout
    "Menu",
    "FooterContent",
]
