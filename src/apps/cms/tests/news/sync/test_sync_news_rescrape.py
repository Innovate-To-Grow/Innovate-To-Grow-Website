from unittest.mock import patch

from django.test import TestCase

from apps.cms.models import NewsArticle
from apps.cms.services.news import sync_news
from apps.cms.tests.news.sync.test_services import SAMPLE_RSS


class SyncNewsTest(TestCase):
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
