from unittest.mock import MagicMock, patch

from django.db import DatabaseError
from django.test import TestCase

from apps.cms.models import NewsArticle
from apps.cms.services.news import sync_news
from apps.cms.services.news.feed_parser import (
    MAX_FEED_BYTES,
    extract_image_url,
    extract_summary,
    fetch_feed,
    parse_pub_date,
)
from apps.cms.services.news.scraper import ARTICLE_REQUEST_HEADERS, MAX_ARTICLE_BYTES, scrape_article
from apps.cms.services.news.url_guard import OversizedNewsResponseError

SAMPLE_RSS = b"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>Test Article One</title>
      <link>https://example.com/article-1</link>
      <description>&lt;p&gt;&lt;img src="https://example.com/img1.jpg" /&gt;&lt;/p&gt;&lt;p&gt;This is the first test article summary text for testing.&lt;/p&gt;</description>
      <pubDate>Mon, 03 Mar 2025 12:00:00 +0000</pubDate>
      <dc:creator>Test Author</dc:creator>
      <guid isPermaLink="false">guid-001</guid>
    </item>
    <item>
      <title>Test Article Two</title>
      <link>https://example.com/article-2</link>
      <description>&lt;p&gt;Second article summary text here for testing purposes.&lt;/p&gt;</description>
      <pubDate>Tue, 04 Mar 2025 12:00:00 +0000</pubDate>
      <dc:creator>Another Author</dc:creator>
      <guid isPermaLink="false">guid-002</guid>
    </item>
  </channel>
</rss>"""


class FeedParserTest(TestCase):
    def test_extract_image_url(self):
        html = '<p><img src="https://example.com/photo.jpg" alt="photo"></p>'
        self.assertEqual(extract_image_url(html), "https://example.com/photo.jpg")

    def test_extract_image_url_no_image(self):
        self.assertEqual(extract_image_url("<p>No image here</p>"), "")

    def test_extract_summary(self):
        html = "<p>Short</p><p>This is a longer paragraph that should be extracted as the summary text.</p>"
        summary = extract_summary(html)
        self.assertEqual(summary, "This is a longer paragraph that should be extracted as the summary text.")

    def test_extract_summary_truncation(self):
        long_text = "A" * 300
        html = f"<p>{long_text}</p>"
        summary = extract_summary(html, max_length=200)
        self.assertLessEqual(len(summary), 204)
        self.assertTrue(summary.endswith("..."))

    def test_parse_pub_date(self):
        dt = parse_pub_date("Mon, 03 Mar 2025 12:00:00 +0000")
        self.assertEqual(dt.year, 2025)
        self.assertEqual(dt.month, 3)
        self.assertEqual(dt.day, 3)

    def test_parse_pub_date_empty(self):
        self.assertIsNone(parse_pub_date(""))

    def test_extract_image_url_empty_html(self):
        self.assertEqual(extract_image_url(""), "")

    def test_extract_summary_empty_html(self):
        self.assertEqual(extract_summary(""), "")

    def test_extract_summary_no_qualifying_paragraph(self):
        # All paragraphs are <= 20 chars, so no summary qualifies.
        self.assertEqual(extract_summary("<p>tiny</p><p>also short</p>"), "")

    @patch("apps.cms.services.news.feed_parser.safe_urlopen")
    def test_fetch_feed_reads_response_bytes(self, mock_open):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"<rss></rss>"
        mock_open.return_value.__enter__.return_value = mock_resp

        result = fetch_feed("https://example.com/feed")

        self.assertEqual(result, b"<rss></rss>")
        # The fetch is routed through the SSRF guard with an identifiable user
        # agent, contact header, and explicit RSS/XML content negotiation.
        self.assertEqual(mock_open.call_args[0][0], "https://example.com/feed")
        headers = mock_open.call_args[1]["headers"]
        self.assertIn("InnovateToGrow", headers["User-Agent"])
        self.assertIn("https://i2g.ucmerced.edu/", headers["User-Agent"])
        self.assertIn("ucmerced.edu", headers["From"])
        self.assertIn("application/rss+xml", headers["Accept"])
        self.assertIn("application/xml", headers["Accept"])

    @patch("apps.cms.services.news.feed_parser.safe_urlopen")
    def test_fetch_feed_rejects_oversized_response(self, mock_open):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"x" * (MAX_FEED_BYTES + 1)
        mock_open.return_value.__enter__.return_value = mock_resp

        with self.assertRaisesRegex(OversizedNewsResponseError, "RSS feed exceeds"):
            fetch_feed("https://example.com/feed")

        mock_resp.read.assert_called_once_with(MAX_FEED_BYTES + 1)


SAMPLE_PAGE_HTML = """
<html>
<body>
<article class="node-news">
  <div class="field-name-field-news-hero-image">
    <img src="https://news.ucmerced.edu/sites/default/files/hero.jpg" alt="Hero" />
  </div>
  <div class="field-name-field-news-hero-caption">
    <div class="field-item">Photo by Jane Doe</div>
  </div>
  <div class="field-name-body">
    <div class="field-item"><p>Full scraped body content here.</p></div>
  </div>
</article>
</body>
</html>
"""


class ScraperTest(TestCase):
    @patch("apps.cms.services.news.scraper.safe_urlopen")
    def test_scrape_article_extracts_fields(self, mock_open):
        mock_resp = mock_open.return_value.__enter__.return_value
        mock_resp.read.return_value = SAMPLE_PAGE_HTML.encode("utf-8")

        result = scrape_article("https://news.ucmerced.edu/news/test")
        self.assertEqual(result["hero_image_url"], "https://news.ucmerced.edu/sites/default/files/hero.jpg")
        self.assertEqual(result["hero_caption"], "Photo by Jane Doe")
        self.assertIn("Full scraped body content", result["body_html"])
        self.assertEqual(mock_open.call_args.kwargs["headers"], ARTICLE_REQUEST_HEADERS)
        self.assertIn("InnovateToGrow-NewsSync", ARTICLE_REQUEST_HEADERS["User-Agent"])
        self.assertEqual(ARTICLE_REQUEST_HEADERS["From"], "i2g@ucmerced.edu")
        self.assertIn("text/html", ARTICLE_REQUEST_HEADERS["Accept"])

    @patch("apps.cms.services.news.scraper.safe_urlopen")
    def test_scrape_article_handles_missing_elements(self, mock_open):
        mock_resp = mock_open.return_value.__enter__.return_value
        mock_resp.read.return_value = b"<html><body><p>Minimal page</p></body></html>"

        result = scrape_article("https://news.ucmerced.edu/news/test")
        self.assertEqual(result["hero_image_url"], "")
        self.assertEqual(result["hero_caption"], "")
        self.assertEqual(result["body_html"], "")

    @patch("apps.cms.services.news.scraper.safe_urlopen")
    def test_scrape_article_relative_image_url(self, mock_open):
        page = '<html><body><article class="node-news"><div class="field-name-field-news-hero-image"><img src="/sites/img.jpg" /></div></article></body></html>'
        mock_resp = mock_open.return_value.__enter__.return_value
        mock_resp.read.return_value = page.encode("utf-8")

        result = scrape_article("https://news.ucmerced.edu/news/test")
        self.assertEqual(result["hero_image_url"], "https://news.ucmerced.edu/sites/img.jpg")

    @patch("apps.cms.services.news.scraper.safe_urlopen")
    def test_scrape_article_rejects_oversized_response(self, mock_open):
        mock_resp = mock_open.return_value.__enter__.return_value
        mock_resp.read.return_value = b"x" * (MAX_ARTICLE_BYTES + 1)

        with self.assertRaisesRegex(OversizedNewsResponseError, "News article exceeds"):
            scrape_article("https://news.ucmerced.edu/news/test")

        mock_resp.read.assert_called_once_with(MAX_ARTICLE_BYTES + 1)


class SyncNewsTest(TestCase):
    @patch("apps.cms.services.news.sync.scrape_article", side_effect=Exception("scrape error"))
    @patch("apps.cms.services.news.sync.fetch_feed")
    def test_sync_creates_articles(self, mock_fetch, mock_scrape):
        mock_fetch.return_value = SAMPLE_RSS
        result = sync_news()
        self.assertEqual(result["created"], 2)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(len(result["errors"]), 0)
        self.assertEqual(len(result["warnings"]), 2)
        self.assertEqual(result["items_seen"], 2)
        self.assertEqual(result["scrape_failed"], 2)
        self.assertEqual(NewsArticle.objects.count(), 2)

    @patch("apps.cms.services.news.sync.scrape_article", side_effect=Exception("scrape error"))
    @patch("apps.cms.services.news.sync.fetch_feed")
    def test_sync_source_key_flows_to_articles(self, mock_fetch, mock_scrape):
        mock_fetch.return_value = SAMPLE_RSS
        sync_news(source_key="custom-source")
        for article in NewsArticle.objects.all():
            self.assertEqual(article.source, "custom-source")

    @patch("apps.cms.services.news.sync.scrape_article")
    @patch("apps.cms.services.news.sync.fetch_feed")
    def test_sync_refreshes_page_only_changes_without_rss_changes(self, mock_fetch, mock_scrape):
        mock_fetch.return_value = SAMPLE_RSS

        def initial_scrape(url):
            slug = url.rsplit("/", 1)[-1]
            return {"hero_image_url": "", "hero_caption": "", "body_html": f"<p>Initial {slug}</p>"}

        mock_scrape.side_effect = initial_scrape
        sync_news()
        mock_scrape.reset_mock()

        def refreshed_scrape(url):
            slug = url.rsplit("/", 1)[-1]
            body = "Updated article-1" if slug == "article-1" else "Initial article-2"
            return {"hero_image_url": "", "hero_caption": "", "body_html": f"<p>{body}</p>"}

        mock_scrape.side_effect = refreshed_scrape

        result = sync_news()

        self.assertEqual(result["created"], 0)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["scrape_failed"], 0)
        self.assertEqual(mock_scrape.call_count, 2)
        self.assertEqual(NewsArticle.objects.get(source_guid="guid-001").content, "<p>Updated article-1</p>")

    @patch("apps.cms.services.news.sync.scrape_article")
    @patch("apps.cms.services.news.sync.fetch_feed")
    def test_sync_counts_changed_metadata_once_while_refreshing_all_pages(self, mock_fetch, mock_scrape):
        mock_fetch.return_value = SAMPLE_RSS
        mock_scrape.return_value = {"hero_image_url": "", "hero_caption": "", "body_html": "<p>Body</p>"}
        sync_news()
        mock_scrape.reset_mock()
        mock_fetch.return_value = SAMPLE_RSS.replace(b"Test Article One", b"Test Article One Updated")

        result = sync_news()

        self.assertEqual(result["created"], 0)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["warnings"], [])
        self.assertEqual(mock_scrape.call_count, 2)
        mock_scrape.assert_any_call("https://example.com/article-1")
        mock_scrape.assert_any_call("https://example.com/article-2")
        self.assertEqual(NewsArticle.objects.get(source_guid="guid-001").title, "Test Article One Updated")

    @patch("apps.cms.services.news.sync.scrape_article", side_effect=Exception("scrape error"))
    @patch("apps.cms.services.news.sync.fetch_feed")
    def test_sync_extracts_fields(self, mock_fetch, mock_scrape):
        mock_fetch.return_value = SAMPLE_RSS
        sync_news()
        article = NewsArticle.objects.get(source_guid="guid-001")
        self.assertEqual(article.title, "Test Article One")
        self.assertEqual(article.source_url, "https://example.com/article-1")
        self.assertEqual(article.author, "Test Author")
        self.assertEqual(article.image_url, "https://example.com/img1.jpg")
        self.assertIn("first test article", article.summary)

    @patch("apps.cms.services.news.sync.scrape_article", side_effect=Exception("scrape error"))
    @patch("apps.cms.services.news.sync.fetch_feed")
    def test_sync_stores_content_fallback_rss(self, mock_fetch, mock_scrape):
        """When scraping fails, RSS description content is preserved."""
        mock_fetch.return_value = SAMPLE_RSS
        sync_news()
        article = NewsArticle.objects.get(source_guid="guid-001")
        self.assertIn("img src", article.content)
        self.assertIn("first test article", article.content)

    @patch("apps.cms.services.news.sync.scrape_article")
    @patch("apps.cms.services.news.sync.fetch_feed")
    def test_sync_updates_with_scraped_content(self, mock_fetch, mock_scrape):
        """When scraping succeeds, hero fields and body are updated."""
        mock_fetch.return_value = SAMPLE_RSS
        mock_scrape.return_value = {
            "hero_image_url": "https://news.ucmerced.edu/hero.jpg",
            "hero_caption": "A caption",
            "body_html": "<p>Scraped body</p>",
        }
        sync_news()
        article = NewsArticle.objects.get(source_guid="guid-001")
        self.assertEqual(article.hero_image_url, "https://news.ucmerced.edu/hero.jpg")
        self.assertEqual(article.hero_caption, "A caption")
        self.assertEqual(article.content, "<p>Scraped body</p>")

        mock_scrape.reset_mock()
        result = sync_news()
        article.refresh_from_db()
        self.assertEqual(result["updated"], 0)
        self.assertEqual(article.content, "<p>Scraped body</p>")
        self.assertEqual(mock_scrape.call_count, 2)

    @patch("apps.cms.services.news.sync.scrape_article")
    @patch("apps.cms.services.news.sync.fetch_feed")
    def test_changed_feed_uses_new_rss_fallback_when_rescrape_fails(self, mock_fetch, mock_scrape):
        mock_fetch.return_value = SAMPLE_RSS
        mock_scrape.return_value = {
            "hero_image_url": "",
            "hero_caption": "",
            "body_html": "<p>Previously scraped body</p>",
        }
        sync_news()

        mock_fetch.return_value = SAMPLE_RSS.replace(
            b"This is the first test article summary text for testing.",
            b"This is the updated first article summary text for testing.",
        )

        def rescrape(url):
            if url.endswith("article-1"):
                raise Exception("rescrape unavailable")
            return {"hero_image_url": "", "hero_caption": "", "body_html": "<p>Previously scraped body</p>"}

        mock_scrape.side_effect = rescrape

        result = sync_news()

        article = NewsArticle.objects.get(source_guid="guid-001")
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["scrape_failed"], 1)
        self.assertEqual(result["errors"], [])
        self.assertTrue(any("rescrape unavailable" in warning for warning in result["warnings"]))
        self.assertIn("updated first article summary", article.content)
        self.assertNotIn("Previously scraped body", article.content)

    @patch("apps.cms.services.news.sync.scrape_article")
    @patch("apps.cms.services.news.sync.fetch_feed")
    def test_title_only_change_preserves_richer_body_when_rescrape_fails(self, mock_fetch, mock_scrape):
        mock_fetch.return_value = SAMPLE_RSS
        mock_scrape.return_value = {
            "hero_image_url": "",
            "hero_caption": "",
            "body_html": "<p>Previously scraped body</p>",
        }
        sync_news()

        mock_fetch.return_value = SAMPLE_RSS.replace(b"Test Article One", b"Test Article One Updated")

        def rescrape(url):
            if url.endswith("article-1"):
                raise Exception("rescrape unavailable")
            return {"hero_image_url": "", "hero_caption": "", "body_html": "<p>Previously scraped body</p>"}

        mock_scrape.side_effect = rescrape

        result = sync_news()

        article = NewsArticle.objects.get(source_guid="guid-001")
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["scrape_failed"], 1)
        self.assertEqual(article.title, "Test Article One Updated")
        self.assertEqual(article.content, "<p>Previously scraped body</p>")

    @patch("apps.cms.services.news.sync.scrape_article")
    @patch("apps.cms.services.news.sync.fetch_feed")
    def test_legacy_blank_raw_payload_preserves_richer_body_when_rescrape_fails(self, mock_fetch, mock_scrape):
        mock_fetch.return_value = SAMPLE_RSS
        mock_scrape.return_value = {
            "hero_image_url": "",
            "hero_caption": "",
            "body_html": "<p>Legacy scraped body</p>",
        }
        sync_news()
        article = NewsArticle.objects.get(source_guid="guid-001")
        article.raw_payload = ""
        article.save(update_fields=["raw_payload"])

        mock_fetch.return_value = SAMPLE_RSS.replace(b"Test Article One", b"Test Article One Updated")

        def rescrape(url):
            if url.endswith("article-1"):
                raise Exception("rescrape unavailable")
            return {"hero_image_url": "", "hero_caption": "", "body_html": "<p>Legacy scraped body</p>"}

        mock_scrape.side_effect = rescrape

        result = sync_news()

        article.refresh_from_db()
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["scrape_failed"], 1)
        self.assertEqual(article.content, "<p>Legacy scraped body</p>")

    @patch("apps.cms.services.news.sync.scrape_article", side_effect=Exception("scrape error"))
    @patch("apps.cms.services.news.sync.fetch_feed", side_effect=Exception("Network error"))
    def test_sync_handles_fetch_error(self, mock_fetch, mock_scrape):
        result = sync_news()
        self.assertEqual(result["created"], 0)
        self.assertGreater(len(result["errors"]), 0)
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["items_seen"], 0)
        self.assertEqual(result["scrape_failed"], 0)

    @patch("apps.cms.services.news.sync.scrape_article")
    @patch("apps.cms.services.news.sync.fetch_feed")
    def test_sync_treats_empty_feed_as_fatal_error(self, mock_fetch, mock_scrape):
        mock_fetch.return_value = b"<?xml version='1.0'?><rss><channel><title>Empty</title></channel></rss>"

        result = sync_news()

        self.assertEqual(result["created"], 0)
        self.assertEqual(result["updated"], 0)
        self.assertTrue(any("no items" in error for error in result["errors"]))
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["items_seen"], 0)
        self.assertEqual(result["scrape_failed"], 0)
        mock_scrape.assert_not_called()

    @patch("apps.cms.services.news.sync.cache.delete", side_effect=RuntimeError("cache unavailable"))
    @patch("apps.cms.services.news.sync.scrape_article")
    @patch("apps.cms.services.news.sync.fetch_feed")
    def test_sync_treats_cache_invalidation_failure_as_warning(self, mock_fetch, mock_scrape, mock_cache_delete):
        mock_fetch.return_value = SAMPLE_RSS
        mock_scrape.return_value = {"hero_image_url": "", "hero_caption": "", "body_html": "<p>Body</p>"}

        result = sync_news()

        self.assertEqual(result["created"], 2)
        self.assertEqual(result["errors"], [])
        self.assertTrue(any("cache" in warning for warning in result["warnings"]))
        mock_cache_delete.assert_called_once_with("news:list")


RSS_NO_GUID = b"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel>
    <item>
      <title>No GUID Article</title>
      <link></link>
      <description>&lt;p&gt;Body&lt;/p&gt;</description>
      <pubDate>Mon, 03 Mar 2025 12:00:00 +0000</pubDate>
      <dc:creator>Author</dc:creator>
      <guid></guid>
    </item>
  </channel>
</rss>"""

RSS_BAD_DATE = b"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel>
    <item>
      <title>Bad Date Article</title>
      <link>https://example.com/bad-date</link>
      <description>&lt;p&gt;Body&lt;/p&gt;</description>
      <pubDate></pubDate>
      <dc:creator>Author</dc:creator>
      <guid isPermaLink="false">guid-bad-date</guid>
    </item>
  </channel>
</rss>"""

RSS_ONE = b"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel>
    <item>
      <title>Single Article</title>
      <link>https://example.com/single</link>
      <description>&lt;p&gt;A reasonably long body paragraph for the summary.&lt;/p&gt;</description>
      <pubDate>Mon, 03 Mar 2025 12:00:00 +0000</pubDate>
      <dc:creator>Author</dc:creator>
      <guid isPermaLink="false">guid-single</guid>
    </item>
  </channel>
</rss>"""

RSS_FILE_SCHEME_LINK = b"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel>
    <item>
      <title>Malicious Link Article</title>
      <link>file:///etc/passwd</link>
      <description>&lt;p&gt;A reasonably long body paragraph for the summary text.&lt;/p&gt;</description>
      <pubDate>Mon, 03 Mar 2025 12:00:00 +0000</pubDate>
      <dc:creator>Author</dc:creator>
      <guid isPermaLink="false">guid-evil-link</guid>
    </item>
  </channel>
</rss>"""


class SyncNewsBranchTest(TestCase):
    @patch("apps.cms.services.news.sync.scrape_article", side_effect=Exception("scrape error"))
    @patch("apps.cms.services.news.sync.fetch_feed")
    def test_sync_skips_item_without_guid_or_link(self, mock_fetch, mock_scrape):
        mock_fetch.return_value = RSS_NO_GUID
        result = sync_news()
        self.assertEqual(result["created"], 0)
        self.assertTrue(any("none were processable" in error for error in result["errors"]))
        self.assertTrue(any("no guid/link" in warning for warning in result["warnings"]))
        self.assertEqual(NewsArticle.objects.count(), 0)

    @patch("apps.cms.services.news.sync.scrape_article", side_effect=Exception("scrape error"))
    @patch("apps.cms.services.news.sync.fetch_feed")
    def test_sync_skips_item_with_invalid_date(self, mock_fetch, mock_scrape):
        mock_fetch.return_value = RSS_BAD_DATE
        result = sync_news()
        self.assertEqual(result["created"], 0)
        self.assertTrue(any("none were processable" in error for error in result["errors"]))
        self.assertTrue(any("invalid date" in warning for warning in result["warnings"]))
        self.assertEqual(NewsArticle.objects.count(), 0)

    @patch("apps.cms.services.news.sync.ET.tostring", side_effect=TypeError("cannot serialize"))
    @patch("apps.cms.services.news.sync.scrape_article", side_effect=Exception("scrape error"))
    @patch("apps.cms.services.news.sync.fetch_feed")
    def test_sync_tolerates_raw_xml_serialize_failure(self, mock_fetch, mock_scrape, mock_tostring):
        mock_fetch.return_value = RSS_ONE
        result = sync_news()
        # Article still created; raw_payload simply stays empty.
        self.assertEqual(result["created"], 1)
        article = NewsArticle.objects.get(source_guid="guid-single")
        self.assertEqual(article.raw_payload, "")
        self.assertTrue(any("serialize raw XML" in warning for warning in result["warnings"]))

    @patch("apps.cms.services.news.sync.scrape_article", side_effect=Exception("scrape error"))
    @patch("apps.cms.services.news.sync.fetch_feed")
    def test_sync_records_item_level_exception(self, mock_fetch, mock_scrape):
        mock_fetch.return_value = RSS_ONE
        with patch(
            "apps.cms.services.news.sync.NewsArticle.objects.get_or_create",
            side_effect=ValueError("db boom"),
        ):
            result = sync_news()
        self.assertTrue(any("none were processable" in error for error in result["errors"]))
        self.assertTrue(any("Error syncing" in warning for warning in result["warnings"]))
        self.assertEqual(NewsArticle.objects.count(), 0)

    @patch("apps.cms.services.news.sync.scrape_article")
    @patch("apps.cms.services.news.sync.fetch_feed")
    def test_sync_records_database_error_as_fatal(self, mock_fetch, mock_scrape):
        mock_fetch.return_value = RSS_ONE
        with patch(
            "apps.cms.services.news.sync.NewsArticle.objects.get_or_create",
            side_effect=DatabaseError("database unavailable"),
        ):
            result = sync_news()

        self.assertTrue(any("Database error syncing" in error for error in result["errors"]))
        self.assertEqual(result["warnings"], [])
        self.assertEqual(NewsArticle.objects.count(), 0)

    @patch("apps.cms.services.news.sync.scrape_article")
    @patch("apps.cms.services.news.sync.fetch_feed")
    def test_sync_treats_cross_source_guid_collision_as_fatal(self, mock_fetch, mock_scrape):
        mock_fetch.return_value = RSS_ONE
        mock_scrape.return_value = {"hero_image_url": "", "hero_caption": "", "body_html": "<p>Body</p>"}
        sync_news(source_key="source-one")
        mock_scrape.reset_mock()

        result = sync_news(source_key="source-two")

        self.assertEqual(result["created"], 0)
        self.assertEqual(result["updated"], 0)
        self.assertTrue(any("GUID collision" in error for error in result["errors"]))
        self.assertEqual(NewsArticle.objects.get(source_guid="guid-single").source, "source-one")
        mock_scrape.assert_not_called()

    @patch("apps.cms.services.news.sync.fetch_feed")
    def test_sync_handles_scrape_worker_exception(self, mock_fetch):
        mock_fetch.return_value = RSS_ONE
        # scrape_article raising inside the worker is caught by _scrape_one;
        # to hit the future.result() exception branch, make _scrape_one raise.
        with patch("apps.cms.services.news.sync._scrape_one", side_effect=RuntimeError("worker crash")):
            result = sync_news()
        # Article was still created in phase 1.
        self.assertEqual(result["created"], 1)
        self.assertEqual(NewsArticle.objects.count(), 1)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["scrape_failed"], 1)
        self.assertTrue(any("worker failure" in warning for warning in result["warnings"]))

    @patch("apps.cms.services.news.sync.scrape_article")
    @patch("apps.cms.services.news.sync.fetch_feed")
    def test_sync_treats_empty_scraped_body_as_warning_and_keeps_rss_fallback(self, mock_fetch, mock_scrape):
        mock_fetch.return_value = RSS_ONE
        mock_scrape.return_value = {"hero_image_url": "", "hero_caption": "", "body_html": ""}

        result = sync_news()

        article = NewsArticle.objects.get(source_guid="guid-single")
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["scrape_failed"], 1)
        self.assertTrue(any("no article body" in warning for warning in result["warnings"]))
        self.assertIn("reasonably long body", article.content)

    @patch("apps.cms.services.news.sync.scrape_article")
    @patch("apps.cms.services.news.sync.fetch_feed")
    def test_sync_records_database_error_applying_scraped_content_as_fatal(self, mock_fetch, mock_scrape):
        mock_fetch.return_value = RSS_ONE
        mock_scrape.return_value = {
            "hero_image_url": "https://example.com/hero.jpg",
            "hero_caption": "Caption",
            "body_html": "<p>Body</p>",
        }
        with patch(
            "apps.cms.services.news.sync.NewsArticle.objects.get",
            side_effect=DatabaseError("read failed"),
        ):
            result = sync_news()

        self.assertEqual(result["created"], 1)
        self.assertEqual(result["scrape_failed"], 1)
        self.assertTrue(any("Database error applying" in error for error in result["errors"]))
        self.assertEqual(result["warnings"], [])

    @patch("apps.cms.services.news.sync.scrape_article")
    @patch("apps.cms.services.news.sync.fetch_feed")
    def test_sync_drops_non_http_link_and_never_scrapes_it(self, mock_fetch, mock_scrape):
        # SSRF defense-in-depth: a file:// link from the remote feed must not be
        # stored as source_url and must not be handed to the scraper.
        mock_fetch.return_value = RSS_FILE_SCHEME_LINK
        result = sync_news()
        self.assertEqual(result["created"], 1)
        article = NewsArticle.objects.get(source_guid="guid-evil-link")
        self.assertEqual(article.source_url, "")
        mock_scrape.assert_not_called()

    @patch("apps.cms.services.news.sync.scrape_article")
    @patch("apps.cms.services.news.sync.fetch_feed")
    def test_sync_handles_article_deleted_before_scrape_update(self, mock_fetch, mock_scrape):
        mock_fetch.return_value = RSS_ONE
        mock_scrape.return_value = {
            "hero_image_url": "https://x/h.jpg",
            "hero_caption": "",
            "body_html": "<p>Body</p>",
        }

        # The phase-2 lookup misses because the row vanished between phases.
        with patch(
            "apps.cms.services.news.sync.NewsArticle.objects.get",
            side_effect=NewsArticle.DoesNotExist,
        ):
            result = sync_news()

        self.assertEqual(result["created"], 1)
        # The DoesNotExist branch is reported as a non-fatal enrichment warning.
        article = NewsArticle.objects.get(source_guid="guid-single")
        self.assertEqual(article.hero_image_url, "")
        self.assertEqual(result["scrape_failed"], 1)
        self.assertTrue(any("disappeared" in warning for warning in result["warnings"]))
