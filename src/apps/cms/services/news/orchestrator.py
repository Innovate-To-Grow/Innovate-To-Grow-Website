"""Shared orchestration for configured news-feed synchronization."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.cms.models import NewsFeedSource, NewsSyncLog

from .sync import sync_news

logger = logging.getLogger(__name__)
_DIAGNOSTIC_MAX_LENGTH = 2000


def _diagnostic_text(value: Any) -> str:
    """Keep persisted/operator-facing diagnostics single-line and bounded."""
    return " ".join(str(value).split())[:_DIAGNOSTIC_MAX_LENGTH]


def _messages(result: dict[str, Any], key: str) -> list[str]:
    values = result.get(key) or []
    if isinstance(values, str):
        values = [values]
    return [message for value in values if (message := _diagnostic_text(value))]


def sync_feed_source(source: NewsFeedSource) -> dict[str, Any]:
    """Synchronize one configured source and persist its attempt metadata."""
    started_at = timezone.now()
    monotonic_started_at = time.monotonic()

    try:
        raw_result = sync_news(feed_url=source.feed_url, source_key=source.source_key)
    except Exception as exc:  # noqa: BLE001 - persist an audit row for an unexpected boundary failure.
        logger.exception("Unexpected news sync failure for source %s", source.source_key)
        raw_result = {"created": 0, "updated": 0, "errors": [str(exc)], "warnings": []}

    duration_seconds = round(time.monotonic() - monotonic_started_at, 2)
    completed_at = timezone.now()
    created = int(raw_result.get("created") or 0)
    updated = int(raw_result.get("updated") or 0)
    errors = _messages(raw_result, "errors")
    warnings = _messages(raw_result, "warnings")
    diagnostics = [*(f"Error: {error}" for error in errors), *(f"Warning: {warning}" for warning in warnings)]
    errors_text = "\n".join(diagnostics)

    if not errors:
        source.last_synced_at = completed_at
    source.last_sync_created = created
    source.last_sync_updated = updated
    source.last_sync_errors = errors_text

    with transaction.atomic():
        update_fields = ["last_sync_created", "last_sync_updated", "last_sync_errors"]
        if not errors:
            update_fields.append("last_synced_at")
        source.save(update_fields=update_fields)
        sync_log = NewsSyncLog.objects.create(
            feed_source=source,
            started_at=started_at,
            duration_seconds=duration_seconds,
            articles_created=created,
            articles_updated=updated,
            errors_text=errors_text,
        )

    return {
        "source": source,
        "sync_log": sync_log,
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_seconds": duration_seconds,
        "created": created,
        "updated": updated,
        "errors": errors,
        "warnings": warnings,
    }


def sync_feed_sources(sources: Iterable[NewsFeedSource]) -> dict[str, Any]:
    """Synchronize configured sources and return aggregate and per-source results."""
    feed_results = [sync_feed_source(source) for source in sources]
    errors: list[str] = []
    warnings: list[str] = []

    for result in feed_results:
        source = result["source"]
        errors.extend(f"{source.name}: {message}" for message in result["errors"])
        warnings.extend(f"{source.name}: {message}" for message in result["warnings"])

    return {
        "feeds": feed_results,
        "feed_count": len(feed_results),
        "created": sum(result["created"] for result in feed_results),
        "updated": sum(result["updated"] for result in feed_results),
        "errors": errors,
        "warnings": warnings,
    }
