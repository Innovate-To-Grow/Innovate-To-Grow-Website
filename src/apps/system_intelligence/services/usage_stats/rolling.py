"""The rolling 24-hour token totals: input, output and cache tokens per turn, and which turns recorded any usage."""

from apps.system_intelligence.models import (
    AssistantMessageLog,
    ChatMessage,
)

_CACHE_READ_TOKEN_KEYS = (
    "cacheReadInputTokens",
    "cache_read_input_tokens",
    "cachedContentTokenCount",
    "cached_content_token_count",
    "promptCacheHitTokens",
    "prompt_cache_hit_tokens",
    "cacheHitTokens",
    "cache_hit_tokens",
)

_CACHE_WRITE_TOKEN_KEYS = (
    "cacheWriteInputTokens",
    "cache_write_input_tokens",
    "cacheCreationInputTokens",
    "cache_creation_input_tokens",
    "promptCacheCreationTokens",
    "prompt_cache_creation_tokens",
    "cacheMissTokens",
    "cache_miss_tokens",
)


def _token_int(usage, key):
    if not isinstance(usage, dict):
        return 0
    try:
        return int(usage.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _token_int_any(usage, keys):
    for key in keys:
        value = _token_int(usage, key)
        if value:
            return value
    return 0


def _empty_rolling_24h():
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "invocations": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "cache_total_tokens": 0,
        "cache_hit_rate": 0,
    }


def _add_cache_tokens(totals, usage):
    totals["cache_read_tokens"] += _token_int_any(usage, _CACHE_READ_TOKEN_KEYS)
    totals["cache_write_tokens"] += _token_int_any(usage, _CACHE_WRITE_TOKEN_KEYS)


def _finalize_cache_metrics(totals):
    cache_total = totals["cache_read_tokens"] + totals["cache_write_tokens"]
    totals["cache_total_tokens"] = cache_total
    totals["cache_hit_rate"] = round((totals["cache_read_tokens"] / cache_total) * 100, 1) if cache_total else 0
    return totals


def _has_recorded_usage(usage):
    return (
        any(_token_int(usage, key) > 0 for key in ("inputTokens", "outputTokens", "totalTokens"))
        or _token_int_any(usage, _CACHE_READ_TOKEN_KEYS) > 0
        or _token_int_any(usage, _CACHE_WRITE_TOKEN_KEYS) > 0
    )


def _rolling_24h(cutoff):
    """Application-recorded model usage over the trailing 24 hours.

    CloudWatch can be unavailable or lag behind the app, so the top-line cards
    use these local audit rows as the authoritative dashboard fallback.
    """
    totals = _empty_rolling_24h()

    message_usages = AssistantMessageLog.objects.filter(created_at__gte=cutoff).values_list("token_usage", flat=True)
    for usage in message_usages:
        totals["input_tokens"] += _token_int(usage, "inputTokens")
        totals["output_tokens"] += _token_int(usage, "outputTokens")
        _add_cache_tokens(totals, usage)
        totals["invocations"] += 1

    admin_messages = ChatMessage.objects.filter(created_at__gte=cutoff, role="assistant").values_list(
        "model_id", "token_usage"
    )
    for model_id, usage in admin_messages:
        totals["input_tokens"] += _token_int(usage, "inputTokens")
        totals["output_tokens"] += _token_int(usage, "outputTokens")
        _add_cache_tokens(totals, usage)
        if model_id or _has_recorded_usage(usage):
            totals["invocations"] += 1

    return _finalize_cache_metrics(totals)
