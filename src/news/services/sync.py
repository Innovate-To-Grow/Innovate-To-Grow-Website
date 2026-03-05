import logging
import xml.etree.ElementTree as ET

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


def sync_news(feed_url: str | None = None) -> dict:
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
                "source": "ucmerced",
            }

            article, was_created = NewsArticle.objects.update_or_create(
                source_guid=guid,
                defaults=defaults,
            )

            # Scrape full page for richer content (hero image, caption, full body)
            try:
                scraped = scrape_article(article.source_url)
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
            except Exception:
                logger.warning("Failed to scrape %s, using RSS content", article.source_url)

            if was_created:
                created += 1
            else:
                updated += 1

        except Exception as e:
            logger.exception("Error syncing item: %s", item.get("guid", "unknown"))
            errors.append(f"Error syncing {item.get('guid', 'unknown')}: {e}")

    cache.delete("news:list")
    return {"created": created, "updated": updated, "errors": errors}
