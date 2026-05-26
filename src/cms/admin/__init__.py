"""
Pages app admin configuration.

Organized into modules by feature:
- layout/: Menu, FooterContent, SiteSettings admin
- cms/: CMSPage admin (block editor, import/export, preview)
- analytics/: PageView admin (read-only dashboard)
"""

from .analytics import PageViewAdmin
from .cms import CMSAssetAdmin, CMSEmbedAllowedHostAdmin, CMSEmbedWidgetAdmin, CMSPageAdmin
from .layout.footer_content import FooterContentAdmin
from .layout.menu import MenuAdmin
from .layout.site_settings import SiteSettingsAdmin
from .layout.style_sheet import StyleSheetAdmin

__all__ = [
    # Layout
    "MenuAdmin",
    "FooterContentAdmin",
    "SiteSettingsAdmin",
    "StyleSheetAdmin",
    # CMS
    "CMSPageAdmin",
    "CMSAssetAdmin",
    "CMSEmbedAllowedHostAdmin",
    "CMSEmbedWidgetAdmin",
    # Analytics
    "PageViewAdmin",
]
