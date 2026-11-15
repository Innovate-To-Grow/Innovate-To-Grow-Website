from unittest.mock import patch

from django.db import DatabaseError
from django.test import TestCase

from apps.cms.models import NewsArticle
from apps.cms.services.news import sync_news
from apps.cms.tests.news.sync.test_services import RSS_BAD_DATE, RSS_FILE_SCHEME_LINK, RSS_NO_GUID, RSS_ONE


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
