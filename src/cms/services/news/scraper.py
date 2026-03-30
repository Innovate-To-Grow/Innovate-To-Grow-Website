import logging
import urllib.request

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_TIMEOUT = 15


def scrape_article(url: str) -> dict:
    """Fetch a UC Merced news page and extract hero image, caption, and body HTML."""
    req = urllib.request.Request(url, headers={"User-Agent": "ITG-News-Scraper/1.0"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310
        html = resp.read().decode("utf-8", errors="replace")

    soup = BeautifulSoup(html, "html.parser")

    hero_image_url = ""
    hero_el = soup.select_one("article.node-news .field-name-field-news-hero-image img")
    if hero_el and hero_el.get("src"):
        hero_image_url = hero_el["src"]
        if hero_image_url.startswith("/"):
            hero_image_url = f"https://news.ucmerced.edu{hero_image_url}"

    hero_caption = ""
    caption_el = soup.select_one(".field-name-field-news-hero-caption .field-item")
    if caption_el:
        hero_caption = caption_el.get_text(strip=True)

    body_html = ""
    body_el = soup.select_one(".field-name-body .field-item")
    if body_el:
        body_html = str(body_el.decode_contents())

    return {
        "hero_image_url": hero_image_url,
        "hero_caption": hero_caption,
        "body_html": body_html,
    }
