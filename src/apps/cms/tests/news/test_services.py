from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.cms.models import NewsArticle
from apps.cms.services.news import sync_news
from apps.cms.services.news.feed_parser import (
    extract_image_url,
    extract_summary,
    fetch_feed,
    parse_pub_date,
)
from apps.cms.services.news.scraper import scrape_article

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
        # The fetch is routed through the SSRF guard with the custom user-agent.
        self.assertEqual(mock_open.call_args[0][0], "https://example.com/feed")
        self.assertEqual(mock_open.call_args[1]["headers"]["User-Agent"], "ITG-NewsSync/1.0")


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


class SyncNewsTest(TestCase):
    @patch("apps.cms.services.news.sync.scrape_article", side_effect=Exception("scrape error"))
    @patch("apps.cms.services.news.sync.fetch_feed")
    def test_sync_creates_articles(self, mock_fetch, mock_scrape):
        mock_fetch.return_value = SAMPLE_RSS
        result = sync_news()
        self.assertEqual(result["created"], 2)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(len(result["errors"]), 0)
        self.assertEqual(NewsArticle.objects.count(), 2)

    @patch("apps.cms.services.news.sync.scrape_article", side_effect=Exception("scrape error"))
    @patch("apps.cms.services.news.sync.fetch_feed")
    def test_sync_source_key_flows_to_articles(self, mock_fetch, mock_scrape):
        mock_fetch.return_value = SAMPLE_RSS
        sync_news(source_key="custom-source")
        for article in NewsArticle.objects.all():
            self.assertEqual(article.source, "custom-source")

    @patch("apps.cms.services.news.sync.scrape_article", side_effect=Exception("scrape error"))
    @patch("apps.cms.services.news.sync.fetch_feed")
    def test_sync_updates_existing(self, mock_fetch, mock_scrape):
        mock_fetch.return_value = SAMPLE_RSS
        sync_news()
        result = sync_news()
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["updated"], 2)

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

    @patch("apps.cms.services.news.sync.scrape_article", side_effect=Exception("scrape error"))
    @patch("apps.cms.services.news.sync.fetch_feed", side_effect=Exception("Network error"))
    def test_sync_handles_fetch_error(self, mock_fetch, mock_scrape):
        result = sync_news()
        self.assertEqual(result["created"], 0)
        self.assertGreater(len(result["errors"]), 0)


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
        self.assertTrue(any("no guid/link" in e for e in result["errors"]))
        self.assertEqual(NewsArticle.objects.count(), 0)

    @patch("apps.cms.services.news.sync.scrape_article", side_effect=Exception("scrape error"))
    @patch("apps.cms.services.news.sync.fetch_feed")
    def test_sync_skips_item_with_invalid_date(self, mock_fetch, mock_scrape):
        mock_fetch.return_value = RSS_BAD_DATE
        result = sync_news()
        self.assertEqual(result["created"], 0)
        self.assertTrue(any("invalid date" in e for e in result["errors"]))
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

    @patch("apps.cms.services.news.sync.scrape_article", side_effect=Exception("scrape error"))
    @patch("apps.cms.services.news.sync.fetch_feed")
    def test_sync_records_item_level_exception(self, mock_fetch, mock_scrape):
        mock_fetch.return_value = RSS_ONE
        with patch(
            "apps.cms.services.news.sync.NewsArticle.objects.update_or_create",
            side_effect=ValueError("db boom"),
        ):
            result = sync_news()
        self.assertTrue(any("Error syncing" in e for e in result["errors"]))
        self.assertEqual(NewsArticle.objects.count(), 0)

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
        mock_scrape.return_value = {"hero_image_url": "https://x/h.jpg", "hero_caption": "", "body_html": ""}

        # The phase-2 lookup misses because the row vanished between phases.
        with patch(
            "apps.cms.services.news.sync.NewsArticle.objects.get",
            side_effect=NewsArticle.DoesNotExist,
        ):
            result = sync_news()

        self.assertEqual(result["created"], 1)
        # The DoesNotExist branch was hit; scrape update was silently skipped.
        article = NewsArticle.objects.get(source_guid="guid-single")
        self.assertEqual(article.hero_image_url, "")
