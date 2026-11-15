from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.cms.services.news.feed_parser import (
    MAX_FEED_BYTES,
    extract_image_url,
    extract_summary,
    fetch_feed,
    parse_pub_date,
)
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
