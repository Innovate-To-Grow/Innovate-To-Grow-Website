"""Page view analytics admin."""

from .admin import PageViewAdmin
from .geo import IP_GEO_CACHE_PREFIX, IP_GEO_CACHE_TTL, ip_geo_lookup_view
from .stats import DASHBOARD_CACHE_KEY, DASHBOARD_CACHE_TTL, compute_dashboard_stats

__all__ = [
    "DASHBOARD_CACHE_KEY",
    "DASHBOARD_CACHE_TTL",
    "IP_GEO_CACHE_PREFIX",
    "IP_GEO_CACHE_TTL",
    "PageViewAdmin",
    "compute_dashboard_stats",
    "ip_geo_lookup_view",
]
