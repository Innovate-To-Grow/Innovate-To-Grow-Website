"""
Pages app admin configuration.

Organized into modules by feature:
- layout/: Menu, FooterContent, SiteSettings admin
- cms/: CMSPage admin (block editor, import/export, preview)
- news/: NewsArticle, NewsFeedSource, NewsSyncLog admin
"""

from .cms import CMSPageAdmin
from .layout.footer_content import FooterContentAdmin
from .layout.menu import MenuAdmin
from .layout.site_settings import SiteSettingsAdmin
from .news import NewsArticleAdmin, NewsFeedSourceAdmin, NewsSyncLogAdmin

__all__ = [
    # Layout
    "MenuAdmin",
    "FooterContentAdmin",
    "SiteSettingsAdmin",
    # CMS
    "CMSPageAdmin",
    # News
    "NewsArticleAdmin",
    "NewsFeedSourceAdmin",
    "NewsSyncLogAdmin",
]
