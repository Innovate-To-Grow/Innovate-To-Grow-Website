"""
Pages app admin configuration.

Organized into modules by model:
- menu: Menu admin
- footer_content: FooterContent admin
"""

from .layout.footer_content import FooterContentAdmin
from .layout.menu import MenuAdmin

__all__ = [
    # Layout
    "MenuAdmin",
    "FooterContentAdmin",
]
