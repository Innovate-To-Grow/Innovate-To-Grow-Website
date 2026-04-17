"""
Pages app admin configuration.

Organized into modules by feature:
- layout/: Menu, FooterContent, SiteSettings admin
- cms/: CMSPage admin (block editor, import/export, preview)
- news/: NewsArticle, NewsFeedSource, NewsSyncLog admin
- analytics/: PageView admin (read-only dashboard)
"""

from .analytics import PageViewAdmin
from .cms import CMSAssetAdmin, CMSEmbedWidgetAdmin, CMSPageAdmin
from .layout.footer_content import FooterContentAdmin
from .layout.menu import MenuAdmin
from .layout.site_settings import SiteSettingsAdmin
from .layout.style_sheet import StyleSheetAdmin
from .news import NewsArticleAdmin, NewsFeedSourceAdmin, NewsSyncLogAdmin

__all__ = [
    # Layout
    "MenuAdmin",
    "FooterContentAdmin",
    "SiteSettingsAdmin",
    "StyleSheetAdmin",
    # CMS
    "CMSPageAdmin",
    "CMSAssetAdmin",
    "CMSEmbedWidgetAdmin",
    # News
    "NewsArticleAdmin",
    "NewsFeedSourceAdmin",
    "NewsSyncLogAdmin",
    # Analytics
    "PageViewAdmin",
]
