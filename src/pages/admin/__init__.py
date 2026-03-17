"""
Pages app admin configuration.

Organized into modules by feature:
- layout/: Menu, FooterContent, GoogleSheetSource, SiteSettings admin
- cms/: CMSPage admin (block editor, import/export, preview)
"""

from .cms import CMSPageAdmin
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
    # CMS
    "CMSPageAdmin",
]
