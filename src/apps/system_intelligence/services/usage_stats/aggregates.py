"""Local (DB-only) usage aggregates for the assistant usage dashboard.

Everything here is pure Django ORM and returns JSON-serializable primitives so
the result can be cached and handed to both a template and a JSON endpoint.

The "admin_chat" token total is summed in Python on purpose: it comes from the
``ChatMessage.token_usage`` JSON column, and JSON-key aggregation differs across
SQLite (dev/test) and PostgreSQL (CI/prod). Pulling the small set of values and
summing in Python keeps the result identical on every backend.
"""

import logging
from datetime import timedelta

from django.db.models import Count, Sum
from django.utils import timezone

from apps.system_intelligence.models import (
    AssistantConversationLog,
    AssistantMessageLog,
    ChatMessage,
)

logger = logging.getLogger(__name__)

# Label the admin AI-chat token bucket distinctly from the public sources.
SOURCE_ADMIN_CHAT = "admin_chat"

_SOURCE_LABELS = {
    AssistantConversationLog.SOURCE_PUBLIC_CHAT: "Public Chat",
    AssistantConversationLog.SOURCE_AI_SEARCH: "AI Search",
    SOURCE_ADMIN_CHAT: "Admin Chat",
}

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


def compute_local_aggregates():
    """Return DB-derived counters, token splits, recents, and top prompts.

    Mirrors the CloudWatch module's guarantee: the dashboard must never 500 on
    stats, so any DB failure degrades to an all-zero payload of the same shape.
    """
    try:
        return _compute()
    except Exception:  # noqa: BLE001 -- defensive: a dashboard must never 500 on local stats.
        logger.exception("Assistant usage local aggregates failed")
        return _empty_aggregates()


def _compute():
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    seven_days_ago = now - timedelta(days=7)
    thirty_days_ago = now - timedelta(days=30)

    return {
        "counts": _counts(today_start, seven_days_ago, thirty_days_ago),
        "rolling_24h": _rolling_24h(now - timedelta(hours=24)),
        "tokens_by_source": _tokens_by_source(thirty_days_ago),
        "recent": _recent_conversations(),
        "top_prompts": _top_prompts(thirty_days_ago),
    }


def _empty_aggregates():
    """The compute_local_aggregates() shape with every value zeroed/empty."""
    return {
        "counts": {
            "conversations_today": 0,
            "conversations_7d": 0,
            "conversations_30d": 0,
            "messages_today": 0,
            "messages_7d": 0,
            "messages_30d": 0,
        },
        "rolling_24h": _empty_rolling_24h(),
        "tokens_by_source": [
            {"source": source, "label": _SOURCE_LABELS[source], "total_tokens": 0}
            for source in (
                AssistantConversationLog.SOURCE_PUBLIC_CHAT,
                AssistantConversationLog.SOURCE_AI_SEARCH,
                SOURCE_ADMIN_CHAT,
            )
        ],
        "recent": [],
        "top_prompts": [],
    }


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


def _counts(today_start, seven_days_ago, thirty_days_ago):
    # One queryset serves both: conversations are counted directly, while
    # "messages" sums the denormalized message_count field on conversations
    # (NOT AssistantMessageLog rows).
    convo_qs = AssistantConversationLog.objects.order_by()

    def convo_count(since):
        return convo_qs.filter(last_activity_at__gte=since).count()

    def message_count(since):
        return convo_qs.filter(last_activity_at__gte=since).aggregate(n=Sum("message_count"))["n"] or 0

    return {
        "conversations_today": convo_count(today_start),
        "conversations_7d": convo_count(seven_days_ago),
        "conversations_30d": convo_count(thirty_days_ago),
        "messages_today": message_count(today_start),
        "messages_7d": message_count(seven_days_ago),
        "messages_30d": message_count(thirty_days_ago),
    }


def _tokens_by_source(thirty_days_ago):
    """Tokens over the trailing 30 days, split by logical source."""
    rows = (
        AssistantConversationLog.objects.filter(last_activity_at__gte=thirty_days_ago)
        .values("source")
        .annotate(total=Sum("total_tokens"))
    )
    by_source = {row["source"]: int(row["total"] or 0) for row in rows}

    # ChatMessage carries admin-chat tokens inside a JSON column; sum in Python
    # so the result is identical on SQLite and PostgreSQL (see module docstring).
    admin_tokens = 0
    usages = ChatMessage.objects.filter(created_at__gte=thirty_days_ago).values_list("token_usage", flat=True)
    for usage in usages:
        if isinstance(usage, dict):
            admin_tokens += int(usage.get("totalTokens") or 0)
    by_source[SOURCE_ADMIN_CHAT] = admin_tokens

    return [
        {"source": source, "label": _SOURCE_LABELS.get(source, source), "total_tokens": by_source.get(source, 0)}
        for source in (
            AssistantConversationLog.SOURCE_PUBLIC_CHAT,
            AssistantConversationLog.SOURCE_AI_SEARCH,
            SOURCE_ADMIN_CHAT,
        )
    ]


def _recent_conversations():
    rows = AssistantConversationLog.objects.order_by("-last_activity_at")[:10]
    return [
        {
            "id": str(row.id),
            "source": row.source,
            "label": row.get_source_display(),
            "session": str(row.session_id)[:8] if row.session_id else "—",
            "message_count": row.message_count,
            "total_tokens": row.total_tokens,
            "last_activity": row.last_activity_at.isoformat(),
        }
        for row in rows
    ]


def _top_prompts(thirty_days_ago):
    """Top 8 public/AI-search prompts by exact-match count over 30 days."""
    rows = (
        AssistantConversationLog.objects.filter(last_activity_at__gte=thirty_days_ago)
        .values("messages__prompt")
        .annotate(count=Count("messages__id"))
        .exclude(messages__prompt__isnull=True)
        .exclude(messages__prompt="")
        .order_by("-count")[:8]
    )
    return [{"prompt": row["messages__prompt"], "count": row["count"]} for row in rows]
