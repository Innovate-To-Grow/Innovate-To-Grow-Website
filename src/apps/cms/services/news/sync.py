import logging
import xml.etree.ElementTree as ET  # noqa: N817
from concurrent.futures import ThreadPoolExecutor, as_completed

from defusedxml import ElementTree as DefusedET
from defusedxml.common import DefusedXmlException
from django.core.cache import cache
from django.db import DatabaseError

from apps.cms.models import NewsArticle

from .feed_parser import fetch_feed, parse_feed_items, parse_pub_date
from .scraper import scrape_article
from .sync_articles import _apply_scrape_result, _feed_defaults
from .sync_run import _diagnostic_text, _exception_text, _feed_failure, _SyncRun

logger = logging.getLogger(__name__)

_SCRAPER_MAX_WORKERS = 4


def _raw_feed_description(raw_payload: str) -> tuple[bool, str]:
    """Return whether a prior raw item has a readable RSS description and its value."""
    if not raw_payload:
        return False, ""
    try:
        description = DefusedET.fromstring(raw_payload).find("description")
    except (ET.ParseError, DefusedXmlException, TypeError, ValueError):
        return False, ""
    if description is None:
        return False, ""
    return True, description.text or ""


def _scrape_one(article_id, source_url: str) -> tuple:
    """Scrape one article and return its result without failing the worker pool."""
    try:
        return article_id, scrape_article(source_url), None
    except Exception as exc:  # noqa: BLE001
        warning = f"Failed to scrape article {article_id}: {_exception_text(exc)}"
        logger.warning("%s; using RSS content", warning)
        return article_id, None, warning


def _apply_feed_defaults(article: NewsArticle, defaults: dict) -> list[str]:
    """Apply changed feed fields and return the fields that actually changed.

    ``content`` is special: after a successful article-page scrape it contains
    richer HTML than the RSS description. Preserve that richer content unless
    the feed description itself changed. A title, author, image, or other item
    change should trigger enrichment without downgrading the existing body when
    that enrichment attempt fails.
    """
    raw_payload_changed = "raw_payload" in defaults and article.raw_payload != defaults["raw_payload"]
    has_prior_feed_content, prior_feed_content = _raw_feed_description(article.raw_payload)
    incoming_feed_content = defaults.get("content")
    feed_content_changed = has_prior_feed_content and prior_feed_content != incoming_feed_content
    changed_fields: list[str] = []

    for name, value in defaults.items():
        if name == "content" and article.content:
            existing_content_is_enriched = has_prior_feed_content and article.content != prior_feed_content
            if (
                not raw_payload_changed
                or not has_prior_feed_content
                or (existing_content_is_enriched and not feed_content_changed)
            ):
                continue
        if getattr(article, name) == value:
            continue
        setattr(article, name, value)
        changed_fields.append(name)

    return changed_fields


def _serialize_raw_item(item: dict, guid, item_label: str, run: _SyncRun) -> str | None:
    try:
        raw_el = ET.Element("item")
        for key, val in item.items():
            child = ET.SubElement(raw_el, key)
            child.text = val
        return ET.tostring(raw_el, encoding="unicode")
    except (TypeError, ValueError):
        logger.debug("Failed to serialize raw XML for %s", item_label)
        run.warnings.append(f"Failed to serialize raw XML for {_diagnostic_text(guid)}")
        return None


def _upsert_item(item: dict, item_label: str, run: _SyncRun) -> None:
    """Phase 1 for one feed item: create or update its article and queue its page for scraping."""
    guid = item["guid"] or item["link"]
    if not guid:
        run.warnings.append(f"Skipping item with no guid/link: {item_label}")
        return
    published_at = parse_pub_date(item["pub_date"])
    if not published_at:
        run.warnings.append(f"Skipping item with invalid date: {_diagnostic_text(guid)}")
        return

    raw = _serialize_raw_item(item, guid, item_label, run)
    defaults = _feed_defaults(item, published_at, run.source_key, raw)
    article, was_created = NewsArticle.objects.get_or_create(source_guid=guid, defaults=defaults)
    if was_created:
        run.created += 1
        run.created_article_ids.add(article.pk)
    elif article.source != run.source_key:
        error = (
            f"Source GUID collision for {_diagnostic_text(guid)}: "
            f"existing source '{_diagnostic_text(article.source)}' does not match "
            f"feed source '{_diagnostic_text(run.source_key)}'"
        )
        logger.error(error)
        run.errors.append(error)
        return
    else:
        changed_fields = _apply_feed_defaults(article, defaults)
        if changed_fields:
            article.save(update_fields=changed_fields)
            run.updated_article_ids.add(article.pk)

    run.processable_items += 1
    # Refresh every valid article page. The page body/hero can change
    # without any corresponding RSS item change, and transient scrape
    # failures must be retried on the next synchronization.
    if article.source_url:
        run.articles_to_scrape[article.pk] = article.source_url


def _scrape_articles(run: _SyncRun) -> None:
    """Phase 2: scrape full pages in parallel for richer content."""
    with ThreadPoolExecutor(max_workers=_SCRAPER_MAX_WORKERS) as pool:
        futures = {pool.submit(_scrape_one, art_id, url): art_id for art_id, url in run.articles_to_scrape.items()}
        for future in as_completed(futures):
            try:
                article_id, scraped, scrape_warning = future.result()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Unexpected error in scrape worker")
                run.warnings.append(
                    f"Unexpected scrape worker failure for article {futures[future]}: {_exception_text(exc)}"
                )
                run.scrape_failed += 1
                continue
            _apply_scrape_result(article_id, scraped, scrape_warning, run)


def sync_news(feed_url: str | None = None, source_key: str = "ucmerced") -> dict:
    """Fetch an RSS feed and upsert articles, separating failures from warnings."""
    try:
        xml_bytes = fetch_feed(feed_url) if feed_url else fetch_feed()
        items = parse_feed_items(xml_bytes)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to fetch/parse RSS feed")
        return _feed_failure(_exception_text(exc))

    if not items:
        error = "RSS feed contained no items"
        logger.error(error)
        return _feed_failure(error)

    run = _SyncRun(source_key=source_key)
    for item in items:
        item_label = _diagnostic_text(item.get("guid") or item.get("title") or "unknown")
        try:
            _upsert_item(item, item_label, run)
        except DatabaseError as exc:
            logger.exception("Database error syncing item: %s", item_label)
            run.errors.append(f"Database error syncing {item_label}: {_exception_text(exc)}")
        except (OSError, ValueError, TypeError, KeyError) as exc:
            logger.exception("Error syncing item: %s", item_label)
            run.warnings.append(f"Error syncing {item_label}: {_exception_text(exc)}")

    if run.processable_items == 0 and not run.errors:
        error = "RSS feed contained items, but none were processable"
        logger.error(error)
        run.errors.append(error)

    if run.articles_to_scrape:
        _scrape_articles(run)

    try:
        cache.delete("news:list")
    except Exception as exc:  # noqa: BLE001 - article writes succeeded; cache failure is non-fatal.
        logger.exception("Failed to invalidate the news list cache after synchronization")
        run.warnings.append(f"Failed to invalidate news list cache: {_exception_text(exc)}")
    return run.summary(len(items))
