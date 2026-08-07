import logging
import xml.etree.ElementTree as ET  # noqa: N817
from concurrent.futures import ThreadPoolExecutor, as_completed

from defusedxml import ElementTree as DefusedET
from defusedxml.common import DefusedXmlException
from django.core.cache import cache
from django.db import DatabaseError

from apps.cms.models import NewsArticle

from .feed_parser import extract_image_url, extract_summary, fetch_feed, parse_feed_items, parse_pub_date
from .scraper import scrape_article
from .url_guard import has_allowed_scheme

logger = logging.getLogger(__name__)

_SCRAPER_MAX_WORKERS = 4
_DIAGNOSTIC_MAX_LENGTH = 2000


def _diagnostic_text(value) -> str:
    """Keep returned/operator-facing diagnostics single-line and bounded."""
    return " ".join(str(value).split())[:_DIAGNOSTIC_MAX_LENGTH]


def _exception_text(exc: Exception) -> str:
    detail = _diagnostic_text(exc)
    return f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__


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

    for field, value in defaults.items():
        if field == "content" and article.content:
            existing_content_is_enriched = has_prior_feed_content and article.content != prior_feed_content
            if (
                not raw_payload_changed
                or not has_prior_feed_content
                or (existing_content_is_enriched and not feed_content_changed)
            ):
                continue
        if getattr(article, field) == value:
            continue
        setattr(article, field, value)
        changed_fields.append(field)

    return changed_fields


def sync_news(feed_url: str | None = None, source_key: str = "ucmerced") -> dict:
    """Fetch an RSS feed and upsert articles, separating failures from warnings."""
    created = 0
    errors: list[str] = []
    warnings: list[str] = []
    scrape_failed = 0
    created_article_ids: set[object] = set()
    updated_article_ids: set[object] = set()

    try:
        xml_bytes = fetch_feed(feed_url) if feed_url else fetch_feed()
        items = parse_feed_items(xml_bytes)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to fetch/parse RSS feed")
        return {
            "created": 0,
            "updated": 0,
            "errors": [_exception_text(exc)],
            "warnings": [],
            "items_seen": 0,
            "scrape_failed": 0,
        }

    items_seen = len(items)
    if not items:
        error = "RSS feed contained no items"
        logger.error(error)
        return {
            "created": 0,
            "updated": 0,
            "errors": [error],
            "warnings": [],
            "items_seen": 0,
            "scrape_failed": 0,
        }

    # Phase 1: parse feed items and upsert article rows.
    articles_to_scrape: dict[object, str] = {}
    processable_items = 0

    for item in items:
        item_label = _diagnostic_text(item.get("guid") or item.get("title") or "unknown")
        try:
            guid = item["guid"] or item["link"]
            if not guid:
                warnings.append(f"Skipping item with no guid/link: {item_label}")
                continue

            published_at = parse_pub_date(item["pub_date"])
            if not published_at:
                warnings.append(f"Skipping item with invalid date: {_diagnostic_text(guid)}")
                continue

            raw = None
            try:
                raw_el = ET.Element("item")
                for key, val in item.items():
                    child = ET.SubElement(raw_el, key)
                    child.text = val
                raw = ET.tostring(raw_el, encoding="unicode")
            except (TypeError, ValueError):
                logger.debug("Failed to serialize raw XML for %s", item_label)
                warnings.append(f"Failed to serialize raw XML for {_diagnostic_text(guid)}")

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

            article, was_created = NewsArticle.objects.get_or_create(
                source_guid=guid,
                defaults=defaults,
            )

            changed_fields: list[str] = []
            if was_created:
                created += 1
                created_article_ids.add(article.pk)
            else:
                if article.source != source_key:
                    error = (
                        f"Source GUID collision for {_diagnostic_text(guid)}: "
                        f"existing source '{_diagnostic_text(article.source)}' does not match "
                        f"feed source '{_diagnostic_text(source_key)}'"
                    )
                    logger.error(error)
                    errors.append(error)
                    continue
                changed_fields = _apply_feed_defaults(article, defaults)
                if changed_fields:
                    article.save(update_fields=changed_fields)
                    updated_article_ids.add(article.pk)

            processable_items += 1

            # Refresh every valid article page. The page body/hero can change
            # without any corresponding RSS item change, and transient scrape
            # failures must be retried on the next synchronization.
            if article.source_url:
                articles_to_scrape[article.pk] = article.source_url

        except DatabaseError as exc:
            logger.exception("Database error syncing item: %s", item_label)
            errors.append(f"Database error syncing {item_label}: {_exception_text(exc)}")
        except (OSError, ValueError, TypeError, KeyError) as exc:
            logger.exception("Error syncing item: %s", item_label)
            warnings.append(f"Error syncing {item_label}: {_exception_text(exc)}")

    if processable_items == 0 and not errors:
        error = "RSS feed contained items, but none were processable"
        logger.error(error)
        errors.append(error)

    # Phase 2: scrape full pages in parallel for richer content.
    if articles_to_scrape:
        with ThreadPoolExecutor(max_workers=_SCRAPER_MAX_WORKERS) as pool:
            futures = {pool.submit(_scrape_one, art_id, url): art_id for art_id, url in articles_to_scrape.items()}
            for future in as_completed(futures):
                try:
                    article_id, scraped, scrape_warning = future.result()
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Unexpected error in scrape worker")
                    warnings.append(
                        f"Unexpected scrape worker failure for article {futures[future]}: {_exception_text(exc)}"
                    )
                    scrape_failed += 1
                    continue

                if scrape_warning:
                    warnings.append(scrape_warning)
                    scrape_failed += 1
                    continue

                if scraped is None:
                    warnings.append(f"Scraper returned no result for article {article_id}")
                    scrape_failed += 1
                    continue

                if not isinstance(scraped, dict) or not scraped.get("body_html"):
                    warnings.append(f"Scraper returned no article body for article {article_id}; using RSS content")
                    scrape_failed += 1
                    continue

                try:
                    article = NewsArticle.objects.get(pk=article_id)
                    scraped_fields = {
                        "hero_image_url": scraped.get("hero_image_url", "")[:1000],
                        "hero_caption": scraped.get("hero_caption", "")[:500],
                        "content": scraped["body_html"],
                    }
                    update_fields = []
                    for field, value in scraped_fields.items():
                        if value and getattr(article, field) != value:
                            setattr(article, field, value)
                            update_fields.append(field)
                    if update_fields:
                        article.save(update_fields=update_fields)
                        if article_id not in created_article_ids:
                            updated_article_ids.add(article_id)
                except NewsArticle.DoesNotExist:
                    logger.warning("Article %s disappeared before scrape update", article_id)
                    warnings.append(f"Article {article_id} disappeared before scrape update")
                    scrape_failed += 1
                except DatabaseError as exc:
                    logger.exception("Database error applying scraped content for article %s", article_id)
                    errors.append(
                        f"Database error applying scraped content for article {article_id}: {_exception_text(exc)}"
                    )
                    scrape_failed += 1
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Failed to apply scraped content for article %s", article_id)
                    warnings.append(f"Failed to apply scraped content for article {article_id}: {_exception_text(exc)}")
                    scrape_failed += 1

    try:
        cache.delete("news:list")
    except Exception as exc:  # noqa: BLE001 - article writes succeeded; cache failure is non-fatal.
        logger.exception("Failed to invalidate the news list cache after synchronization")
        warnings.append(f"Failed to invalidate news list cache: {_exception_text(exc)}")
    return {
        "created": created,
        "updated": len(updated_article_ids),
        "errors": errors,
        "warnings": warnings,
        "items_seen": items_seen,
        "scrape_failed": scrape_failed,
    }
