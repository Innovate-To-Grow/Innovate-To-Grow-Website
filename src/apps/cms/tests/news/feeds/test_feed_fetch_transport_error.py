from http.client import IncompleteRead
from unittest.mock import call, patch
from urllib.error import URLError

from django.test import SimpleTestCase

from apps.cms.services.news.feed_errors import FeedFetchError
from apps.cms.services.news.feed_parser import fetch_feed
from apps.cms.tests.news.feeds.test_feed_fetch_errors import _successful_response


class FeedFetchTransportErrorTest(SimpleTestCase):
    @patch("apps.cms.services.news.feed_parser.time.sleep")
    @patch("apps.cms.services.news.feed_parser.safe_urlopen")
    def test_url_error_is_retried_then_can_succeed(self, mock_open, mock_sleep):
        context, _response = _successful_response(b"<rss>recovered</rss>")
        mock_open.side_effect = [URLError("temporary connection failure"), context]

        result = fetch_feed("https://news.ucmerced.edu/feed")

        self.assertEqual(result, b"<rss>recovered</rss>")
        self.assertEqual(mock_open.call_count, 2)
        mock_sleep.assert_called_once_with(0.25)

    @patch("apps.cms.services.news.feed_parser.time.sleep")
    @patch("apps.cms.services.news.feed_parser.safe_urlopen")
    def test_timeout_is_bounded_and_reported_without_query_data(self, mock_open, mock_sleep):
        mock_open.side_effect = TimeoutError("socket stalled\nwith control text")

        with self.assertRaises(FeedFetchError) as raised:
            fetch_feed("https://news.ucmerced.edu/feed?credential=secret")

        error = raised.exception
        self.assertIsNone(error.status)
        self.assertEqual(error.final_url, "https://news.ucmerced.edu/feed")
        self.assertEqual(error.reason, "socket stalled with control text")
        self.assertTrue(error.retryable)
        self.assertEqual(error.attempts, 3)
        self.assertNotIn("secret", str(error))
        self.assertEqual(mock_open.call_count, 3)
        self.assertEqual(mock_sleep.call_args_list, [call(0.25), call(0.5)])

    @patch("apps.cms.services.news.feed_parser.time.sleep")
    @patch("apps.cms.services.news.feed_parser.safe_urlopen")
    def test_exhausted_url_error_is_structured(self, mock_open, mock_sleep):
        mock_open.side_effect = URLError("connection reset")

        with self.assertRaises(FeedFetchError) as raised:
            fetch_feed("https://news.ucmerced.edu/feed")

        error = raised.exception
        self.assertIsNone(error.status)
        self.assertEqual(error.reason, "connection reset")
        self.assertTrue(error.retryable)
        self.assertEqual(error.attempts, 3)
        self.assertEqual(mock_open.call_count, 3)
        self.assertEqual(mock_sleep.call_args_list, [call(0.25), call(0.5)])

    @patch("apps.cms.services.news.feed_parser.time.sleep")
    @patch("apps.cms.services.news.feed_parser.safe_urlopen")
    def test_connection_reset_during_response_read_is_retried(self, mock_open, mock_sleep):
        first_context, first_response = _successful_response()
        first_response.read.side_effect = ConnectionResetError("peer reset the connection")
        recovered_context, _recovered_response = _successful_response(b"<rss>recovered</rss>")
        mock_open.side_effect = [first_context, recovered_context]

        result = fetch_feed("https://news.ucmerced.edu/feed")

        self.assertEqual(result, b"<rss>recovered</rss>")
        self.assertEqual(mock_open.call_count, 2)
        mock_sleep.assert_called_once_with(0.25)

    @patch("apps.cms.services.news.feed_parser.time.sleep")
    @patch("apps.cms.services.news.feed_parser.safe_urlopen")
    def test_incomplete_response_read_is_bounded_and_structured(self, mock_open, mock_sleep):
        contexts = []
        for _attempt in range(3):
            context, response = _successful_response()
            response.read.side_effect = IncompleteRead(b"partial", 100)
            contexts.append(context)
        mock_open.side_effect = contexts

        with self.assertRaises(FeedFetchError) as raised:
            fetch_feed("https://news.ucmerced.edu/feed")

        self.assertTrue(raised.exception.retryable)
        self.assertEqual(raised.exception.attempts, 3)
        self.assertEqual(mock_sleep.call_args_list, [call(0.25), call(0.5)])
