"""
Pages app models export.

Aggregates commonly used models so callers can import from `pages.models`.
"""

from .pages import (
    BLOCK_SCHEMAS,
    BLOCK_TYPE_CHOICES,
    BLOCK_TYPE_KEYS,
    CMSBlock,
    CMSPage,
    FooterContent,
    Menu,
    NewsArticle,
    NewsFeedSource,
    NewsSyncLog,
    SiteSettings,
    validate_block_data,
)

__all__ = [
    # Layout
    "Menu",
    "FooterContent",
    "SiteSettings",
    # CMS
    "CMSPage",
    "CMSBlock",
    "BLOCK_TYPE_CHOICES",
    "BLOCK_TYPE_KEYS",
    "BLOCK_SCHEMAS",
    "validate_block_data",
    # News
    "NewsArticle",
    "NewsFeedSource",
    "NewsSyncLog",
]
