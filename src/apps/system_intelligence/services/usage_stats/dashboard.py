"""Compose the assistant usage dashboard context behind Django's cache.

CloudWatch reads are cached longer (they hit AWS and change slowly); the local
DB aggregates are cached briefly so the dashboard stays cheap to refresh -- e.g.
the TV-mode auto-refresh polling the data endpoint.
"""

from django.core.cache import cache

from .aggregates import compute_local_aggregates
from .cloudwatch import fetch_bedrock_metrics

CLOUDWATCH_CACHE_KEY = "assistant:usage:cloudwatch"
CLOUDWATCH_CACHE_TTL = 600
LOCAL_CACHE_KEY = "assistant:usage:local"
LOCAL_CACHE_TTL = 300


def get_dashboard_context(force=False):
    """Return the merged dashboard context (CloudWatch + local aggregates).

    With ``force=True`` the cache read is skipped (both halves recompute) but
    the fresh values are still written back so subsequent reads stay warm.
    """
    cloudwatch = None if force else cache.get(CLOUDWATCH_CACHE_KEY)
    if cloudwatch is None:
        cloudwatch = fetch_bedrock_metrics()
        cache.set(CLOUDWATCH_CACHE_KEY, cloudwatch, CLOUDWATCH_CACHE_TTL)

    local = None if force else cache.get(LOCAL_CACHE_KEY)
    if local is None:
        local = compute_local_aggregates()
        cache.set(LOCAL_CACHE_KEY, local, LOCAL_CACHE_TTL)

    return {"cloudwatch": cloudwatch, "local": local}
