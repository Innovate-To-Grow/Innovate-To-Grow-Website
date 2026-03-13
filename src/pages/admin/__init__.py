"""
Pages app admin configuration.

Organized into modules by model:
- menu: Menu admin
- footer_content: FooterContent admin
"""

from .layout.footer_content import FooterContentAdmin
from .layout.google_sheet_source import GoogleSheetSourceAdmin
from .layout.menu import MenuAdmin
from .layout.site_settings import SiteSettingsAdmin

__all__ = [
    # Layout
    "MenuAdmin",
    "FooterContentAdmin",
    "GoogleSheetSourceAdmin",
    "SiteSettingsAdmin",
]
