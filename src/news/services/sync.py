import logging
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.cache import cache

from ..models import NewsArticle
from .feed_parser import (
    extract_image_url,
    extract_summary,
    fetch_feed,
    parse_feed_items,
    parse_pub_date,
)
from .scraper import scrape_article

logger = logging.getLogger(__name__)

_SCRAPER_MAX_WORKERS = 4


def _scrape_one(article_id, source_url: str) -> tuple:
    """Scrape a single article page. Returns (article_id, scraped_dict | None)."""
    try:
        return article_id, scrape_article(source_url)
    except Exception:
        logger.warning("Failed to scrape %s, using RSS content", source_url)
        return article_id, None


def sync_news(feed_url: str | None = None, source_key: str = "ucmerced") -> dict:
    """Fetch RSS feed and upsert articles. Returns sync stats."""
    created = 0
    updated = 0
    errors: list[str] = []

    try:
        xml_bytes = fetch_feed(feed_url) if feed_url else fetch_feed()
        items = parse_feed_items(xml_bytes)
    except Exception as e:
        logger.exception("Failed to fetch/parse RSS feed")
        return {"created": 0, "updated": 0, "errors": [str(e)]}

    # Phase 1: Parse feed items and create/update article rows from RSS data.
    articles_to_scrape: list[tuple] = []  # (article_id, source_url)

    for item in items:
        try:
            guid = item["guid"] or item["link"]
            if not guid:
                errors.append(f"Skipping item with no guid/link: {item.get('title', 'unknown')}")
                continue

            published_at = parse_pub_date(item["pub_date"])
            if not published_at:
                errors.append(f"Skipping item with invalid date: {guid}")
                continue

            # Serialize raw XML for debugging
            raw = ""
            try:
                raw_el = ET.Element("item")
                for key, val in item.items():
                    child = ET.SubElement(raw_el, key)
                    child.text = val
                raw = ET.tostring(raw_el, encoding="unicode")
            except Exception:
                logger.debug("Failed to serialize raw XML for item: %s", item.get("guid", "unknown"))

            defaults = {
                "title": item["title"][:500],
                "source_url": item["link"][:1000],
                "summary": extract_summary(item["description"]),
                "image_url": extract_image_url(item["description"])[:1000],
                "content": item["description"],
                "author": item["creator"][:255],
                "published_at": published_at,
                "raw_payload": raw,
                "source": source_key,
            }

            article, was_created = NewsArticle.objects.update_or_create(
                source_guid=guid,
                defaults=defaults,
            )

            articles_to_scrape.append((article.pk, article.source_url))

            if was_created:
                created += 1
            else:
                updated += 1

        except Exception as e:
            logger.exception("Error syncing item: %s", item.get("guid", "unknown"))
            errors.append(f"Error syncing {item.get('guid', 'unknown')}: {e}")

    # Phase 2: Scrape full pages in parallel for richer content.
    if articles_to_scrape:
        with ThreadPoolExecutor(max_workers=_SCRAPER_MAX_WORKERS) as executor:
            futures = {executor.submit(_scrape_one, art_id, url): art_id for art_id, url in articles_to_scrape}
            for future in as_completed(futures):
                try:
                    article_id, scraped = future.result()
                except Exception:
                    logger.exception("Unexpected error in scrape worker")
                    continue

                if scraped is None:
                    continue

                try:
                    article = NewsArticle.objects.get(pk=article_id)
                    update_fields = []
                    if scraped["hero_image_url"]:
                        article.hero_image_url = scraped["hero_image_url"][:1000]
                        update_fields.append("hero_image_url")
                    if scraped["hero_caption"]:
                        article.hero_caption = scraped["hero_caption"][:500]
                        update_fields.append("hero_caption")
                    if scraped["body_html"]:
                        article.content = scraped["body_html"]
                        update_fields.append("content")
                    if update_fields:
                        article.save(update_fields=update_fields)
                except NewsArticle.DoesNotExist:
                    logger.warning("Article %s disappeared before scrape update", article_id)

    cache.delete("news:list")
    return {"created": created, "updated": updated, "errors": errors}
