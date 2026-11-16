from unittest.mock import patch

from django.test import TestCase

from apps.cms.services.news.scraper import ARTICLE_REQUEST_HEADERS, MAX_ARTICLE_BYTES, scrape_article
from apps.cms.services.news.url_guard import OversizedNewsResponseError
from apps.cms.tests.news.sync.test_services import SAMPLE_PAGE_HTML


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
