"""
Layout app models export.

Contains models for site-wide layout components like Footer and Menu.
"""

from .footer_content import FooterContent
from .menu import Menu, MenuPageLink

__all__ = [
    "FooterContent",
    "Menu",
    "MenuPageLink",
]
