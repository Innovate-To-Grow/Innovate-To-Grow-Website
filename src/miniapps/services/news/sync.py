import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.db import DatabaseError

from miniapps.models import MiniApp, MiniAppDataRecord

from .feed_parser import extract_image_url, extract_summary, fetch_feed, parse_feed_items, parse_pub_date
from .scraper import scrape_article

logger = logging.getLogger(__name__)

_SCRAPER_MAX_WORKERS = 4
NEWS_APP_SLUG = "news"


def _scrape_one(record_id, source_url: str) -> tuple:
    try:
        return record_id, scrape_article(source_url)
    except Exception:  # noqa: BLE001
        logger.warning("Failed to scrape %s, using RSS content", source_url)
        return record_id, None


def sync_news(feed_url: str | None = None, source_key: str = "ucmerced") -> dict:
    """Fetch RSS feed and upsert articles into MiniAppDataRecord. Returns sync stats."""
    created = 0
    updated = 0
    errors: list[str] = []

    try:
        app = MiniApp.objects.get(slug=NEWS_APP_SLUG)
    except MiniApp.DoesNotExist:
        return {"created": 0, "updated": 0, "errors": ["News MiniApp not found. Run migrations first."]}

    try:
        xml_bytes = fetch_feed(feed_url) if feed_url else fetch_feed()
        items = parse_feed_items(xml_bytes)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to fetch/parse RSS feed")
        return {"created": 0, "updated": 0, "errors": [str(exc)]}

    records_to_scrape: list[tuple] = []

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

            data = {
                "title": item["title"][:500],
                "source_url": item["link"][:1000],
                "summary": extract_summary(item["description"]),
                "image_url": extract_image_url(item["description"])[:1000],
                "content": item["description"],
                "author": item["creator"][:255],
                "published_at": published_at.isoformat(),
                "source": source_key,
                "source_guid": guid,
                "hero_image_url": "",
                "hero_caption": "",
            }

            existing = app.records.filter(data__source_guid=guid).first()
            if existing:
                existing.data = {**existing.data, **data}
                existing.save()
                records_to_scrape.append((existing.pk, data["source_url"]))
                updated += 1
            else:
                record = MiniAppDataRecord.objects.create(app=app, data=data)
                records_to_scrape.append((record.pk, data["source_url"]))
                created += 1

        except (OSError, ValueError, TypeError, KeyError, DatabaseError) as exc:
            logger.exception("Error syncing item: %s", item.get("guid", "unknown"))
            errors.append(f"Error syncing {item.get('guid', 'unknown')}: {exc}")

    if records_to_scrape:
        with ThreadPoolExecutor(max_workers=_SCRAPER_MAX_WORKERS) as pool:
            futures = {pool.submit(_scrape_one, rec_id, url): rec_id for rec_id, url in records_to_scrape}
            for future in as_completed(futures):
                try:
                    record_id, scraped = future.result()
                except Exception:  # noqa: BLE001
                    logger.exception("Unexpected error in scrape worker")
                    continue

                if scraped is None:
                    continue

                try:
                    record = MiniAppDataRecord.objects.get(pk=record_id)
                    changed = False
                    if scraped["hero_image_url"]:
                        record.data["hero_image_url"] = scraped["hero_image_url"][:1000]
                        changed = True
                    if scraped["hero_caption"]:
                        record.data["hero_caption"] = scraped["hero_caption"][:500]
                        changed = True
                    if scraped["body_html"]:
                        record.data["content"] = scraped["body_html"]
                        changed = True
                    if changed:
                        record.save()
                except MiniAppDataRecord.DoesNotExist:
                    logger.warning("Record %s disappeared before scrape update", record_id)

    return {"created": created, "updated": updated, "errors": errors}
