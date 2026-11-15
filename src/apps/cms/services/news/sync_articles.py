"""News sync: the article field values a feed item gives, and storing what the scraper returned."""

import logging

from django.db import DatabaseError

from apps.cms.models import NewsArticle

from .feed_parser import extract_image_url, extract_summary
from .sync_run import _exception_text, _SyncRun
from .url_guard import has_allowed_scheme

# The same logger as sync.py, so these records keep the name they were logged under before the split.
logger = logging.getLogger("apps.cms.services.news.sync")


def _feed_defaults(item: dict, published_at, source_key: str, raw: str | None) -> dict:
    # The link is attacker-influenced (it comes straight from the remote
    # feed). Only persist/scrape http(s) URLs so a file:// or javascript:
    # link can never be stored as a rendered href or fetched by the
    # scraper. The fetch itself is additionally IP/redirect-guarded.
    raw_link = item["link"]
    safe_link = raw_link[:1000] if has_allowed_scheme(raw_link) else ""
    defaults = {
        "title": item["title"][:500],
        "source_url": safe_link,
        "summary": extract_summary(item["description"]),
        "image_url": extract_image_url(item["description"])[:1000],
        "content": item["description"],
        "author": item["creator"][:255],
        "published_at": published_at,
        "source": source_key,
    }
    if raw is not None:
        defaults["raw_payload"] = raw
    return defaults


def _store_scraped_content(article_id, scraped: dict, run: _SyncRun) -> None:
    article = NewsArticle.objects.get(pk=article_id)
    scraped_fields = {
        "hero_image_url": scraped.get("hero_image_url", "")[:1000],
        "hero_caption": scraped.get("hero_caption", "")[:500],
        "content": scraped["body_html"],
    }
    update_fields = []
    for name, value in scraped_fields.items():
        if value and getattr(article, name) != value:
            setattr(article, name, value)
            update_fields.append(name)
    if update_fields:
        article.save(update_fields=update_fields)
        if article_id not in run.created_article_ids:
            run.updated_article_ids.add(article_id)


def _usable_scrape(article_id, scraped, scrape_warning, run: _SyncRun) -> bool:
    """Record why a scrape result cannot replace the RSS content; True when it can."""
    if scrape_warning:
        run.warnings.append(scrape_warning)
    elif scraped is None:
        run.warnings.append(f"Scraper returned no result for article {article_id}")
    elif not isinstance(scraped, dict) or not scraped.get("body_html"):
        run.warnings.append(f"Scraper returned no article body for article {article_id}; using RSS content")
    else:
        return True
    run.scrape_failed += 1
    return False


def _apply_scrape_result(article_id, scraped, scrape_warning, run: _SyncRun) -> None:
    if not _usable_scrape(article_id, scraped, scrape_warning, run):
        return
    try:
        _store_scraped_content(article_id, scraped, run)
    except NewsArticle.DoesNotExist:
        logger.warning("Article %s disappeared before scrape update", article_id)
        run.warnings.append(f"Article {article_id} disappeared before scrape update")
        run.scrape_failed += 1
    except DatabaseError as exc:
        logger.exception("Database error applying scraped content for article %s", article_id)
        run.errors.append(f"Database error applying scraped content for article {article_id}: {_exception_text(exc)}")
        run.scrape_failed += 1
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to apply scraped content for article %s", article_id)
        run.warnings.append(f"Failed to apply scraped content for article {article_id}: {_exception_text(exc)}")
        run.scrape_failed += 1
