from .analytics import PageViewCreateSerializer
from .cms import CMSBlockSerializer, CMSPageSerializer
from .news import NewsArticleDetailSerializer, NewsArticleSerializer
from .serializers import FooterContentSerializer, MenuSerializer

__all__ = [
    "MenuSerializer",
    "FooterContentSerializer",
    "CMSBlockSerializer",
    "CMSPageSerializer",
    "NewsArticleSerializer",
    "NewsArticleDetailSerializer",
    "PageViewCreateSerializer",
]
