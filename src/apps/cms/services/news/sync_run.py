"""News sync: the record of one run (counts, errors, warnings) and its bounded diagnostic text."""

from dataclasses import dataclass, field

_DIAGNOSTIC_MAX_LENGTH = 2000


def _diagnostic_text(value) -> str:
    """Keep returned/operator-facing diagnostics single-line and bounded."""
    return " ".join(str(value).split())[:_DIAGNOSTIC_MAX_LENGTH]


def _exception_text(exc: Exception) -> str:
    detail = _diagnostic_text(exc)
    return f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__


@dataclass
class _SyncRun:
    """What one synchronization has done so far; becomes the returned summary."""

    source_key: str
    created: int = 0
    scrape_failed: int = 0
    processable_items: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    created_article_ids: set = field(default_factory=set)
    updated_article_ids: set = field(default_factory=set)
    articles_to_scrape: dict = field(default_factory=dict)

    def summary(self, items_seen: int) -> dict:
        return {
            "created": self.created,
            "updated": len(self.updated_article_ids),
            "errors": self.errors,
            "warnings": self.warnings,
            "items_seen": items_seen,
            "scrape_failed": self.scrape_failed,
        }


def _feed_failure(error: str) -> dict:
    return {"created": 0, "updated": 0, "errors": [error], "warnings": [], "items_seen": 0, "scrape_failed": 0}
