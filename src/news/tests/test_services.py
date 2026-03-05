from unittest.mock import patch

from django.test import TestCase

from news.models import NewsArticle
from news.services import sync_news
from news.services.feed_parser import extract_image_url, extract_summary, parse_pub_date

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
        self.assertTrue(len(summary) <= 204)  # 200 + "..."
        self.assertTrue(summary.endswith("..."))

    def test_parse_pub_date(self):
        dt = parse_pub_date("Mon, 03 Mar 2025 12:00:00 +0000")
        self.assertEqual(dt.year, 2025)
        self.assertEqual(dt.month, 3)
        self.assertEqual(dt.day, 3)

    def test_parse_pub_date_empty(self):
        self.assertIsNone(parse_pub_date(""))


class SyncNewsTest(TestCase):
    @patch("news.services.sync.fetch_feed")
    def test_sync_creates_articles(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_RSS
        result = sync_news()
        self.assertEqual(result["created"], 2)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(len(result["errors"]), 0)
        self.assertEqual(NewsArticle.objects.count(), 2)

    @patch("news.services.sync.fetch_feed")
    def test_sync_updates_existing(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_RSS
        sync_news()
        result = sync_news()
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["updated"], 2)

    @patch("news.services.sync.fetch_feed")
    def test_sync_extracts_fields(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_RSS
        sync_news()
        article = NewsArticle.objects.get(source_guid="guid-001")
        self.assertEqual(article.title, "Test Article One")
        self.assertEqual(article.source_url, "https://example.com/article-1")
        self.assertEqual(article.author, "Test Author")
        self.assertEqual(article.image_url, "https://example.com/img1.jpg")
        self.assertIn("first test article", article.summary)

    @patch("news.services.sync.fetch_feed", side_effect=Exception("Network error"))
    def test_sync_handles_fetch_error(self, mock_fetch):
        result = sync_news()
        self.assertEqual(result["created"], 0)
        self.assertGreater(len(result["errors"]), 0)
