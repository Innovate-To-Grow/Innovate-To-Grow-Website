from .cms_asset import CMSAssetAdmin
from .cms_page import CMSPageAdmin
from .embed.allowed_host import CMSEmbedAllowedHostAdmin
from .embed.widget import CMSEmbedWidgetAdmin
from .route_redirect import RouteRedirectAdmin

__all__ = [
    "CMSAssetAdmin",
    "CMSEmbedAllowedHostAdmin",
    "CMSEmbedWidgetAdmin",
    "CMSPageAdmin",
    "RouteRedirectAdmin",
]
