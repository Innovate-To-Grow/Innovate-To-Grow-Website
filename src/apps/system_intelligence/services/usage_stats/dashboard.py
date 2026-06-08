"""Compose the assistant usage dashboard context behind Django's cache."""

from django.core.cache import cache

from .cloudwatch import fetch_bedrock_metrics

CLOUDWATCH_CACHE_KEY = "assistant:usage:cloudwatch"
CLOUDWATCH_CACHE_TTL = 600
LOCAL_CACHE_KEY = "assistant:usage:local"


def get_dashboard_context(force=False):
    """Return the CloudWatch-backed dashboard context.

    With ``force=True`` the cache read is skipped but the fresh value is still
    written back so subsequent reads stay warm.
    """
    cloudwatch = None if force else cache.get(CLOUDWATCH_CACHE_KEY)
    if cloudwatch is None:
        cloudwatch = fetch_bedrock_metrics()
        cache.set(CLOUDWATCH_CACHE_KEY, cloudwatch, CLOUDWATCH_CACHE_TTL)

    return {"cloudwatch": cloudwatch}
