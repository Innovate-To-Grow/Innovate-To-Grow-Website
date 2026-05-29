from .analytics import PageViewCreateSerializer
from .cms import CMSBlockSerializer, CMSPageSerializer
from .layout import FooterContentSerializer, MenuSerializer
from .news import NewsArticleDetailSerializer, NewsArticleSerializer

__all__ = [
    "MenuSerializer",
    "FooterContentSerializer",
    "CMSBlockSerializer",
    "CMSPageSerializer",
    "NewsArticleSerializer",
    "NewsArticleDetailSerializer",
    "PageViewCreateSerializer",
]
