from unittest.mock import patch

from django.test import TestCase

from apps.cms.models import NewsArticle
from apps.cms.services.news import sync_news
from apps.cms.tests.news.sync.test_services import SAMPLE_RSS


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
