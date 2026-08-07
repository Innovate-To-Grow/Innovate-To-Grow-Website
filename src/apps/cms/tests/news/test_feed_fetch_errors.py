from email.message import Message
from http.client import IncompleteRead
from io import BytesIO
from unittest.mock import MagicMock, call, patch
from urllib.error import HTTPError, URLError

from django.test import SimpleTestCase

from apps.cms.services.news.feed_parser import (
    _ERROR_BODY_BYTES,
    FEED_REQUEST_HEADERS,
    FeedFetchError,
    fetch_feed,
)


def _http_error(
    status: int,
    *,
    url: str = "https://news.ucmerced.edu/feed",
    body: bytes = b"",
    content_type: str = "text/html; charset=utf-8",
) -> HTTPError:
    headers = Message()
    headers["Content-Type"] = content_type
    return HTTPError(url, status, "upstream failure", headers, BytesIO(body))


def _successful_response(payload: bytes = b"<rss></rss>"):
    response = MagicMock()
    response.read.return_value = payload
    context = MagicMock()
    context.__enter__.return_value = response
    context.__exit__.return_value = False
    return context, response


class FeedFetchRequestTest(SimpleTestCase):
    @patch("apps.cms.services.news.feed_parser.safe_urlopen")
    def test_sends_identifying_user_agent_and_rss_accept_header(self, mock_open):
        context, response = _successful_response()
        mock_open.return_value = context

        result = fetch_feed("https://news.ucmerced.edu/feed")

        self.assertEqual(result, b"<rss></rss>")
        request_headers = mock_open.call_args.kwargs["headers"]
        self.assertEqual(request_headers, FEED_REQUEST_HEADERS)
        self.assertEqual(
            request_headers["User-Agent"],
            "InnovateToGrow-NewsSync/1.0 (+https://i2g.ucmerced.edu/)",
        )
        self.assertEqual(request_headers["From"], "i2g@ucmerced.edu")
        self.assertIn("application/rss+xml", request_headers["Accept"])
        response.read.assert_called_once()


class FeedFetchHttpErrorTest(SimpleTestCase):
    @patch("apps.cms.services.news.feed_parser.time.sleep")
    @patch("apps.cms.services.news.feed_parser.safe_urlopen")
    def test_403_is_not_retried_and_keeps_sanitized_akamai_details(self, mock_open, mock_sleep):
        body_reader = MagicMock()
        body_reader.read.return_value = (
            b"<html><h1>Access Denied</h1>"
            b"<p>Reference&#32;&#35;18&#46;6c9fd817&#46;1786110126&#46;5cbfd86</p>"
            b"<p>private upstream details must not be persisted</p></html>"
        )
        headers = Message()
        headers["Content-Type"] = "text/html; charset=utf-8"
        mock_open.side_effect = HTTPError(
            "https://news.ucmerced.edu/feed?token=top-secret#private",
            403,
            "Forbidden\r\n",
            headers,
            body_reader,
        )

        with self.assertRaises(FeedFetchError) as raised:
            fetch_feed("https://news.ucmerced.edu/feed?token=top-secret#private")

        error = raised.exception
        self.assertEqual(error.status, 403)
        self.assertEqual(error.final_url, "https://news.ucmerced.edu/feed")
        self.assertEqual(error.content_type, "text/html")
        self.assertEqual(error.akamai_reference, "18.6c9fd817.1786110126.5cbfd86")
        self.assertEqual(error.reason, "Forbidden")
        self.assertFalse(error.retryable)
        self.assertEqual(error.attempts, 1)
        self.assertIn("akamai_reference=18.6c9fd817.1786110126.5cbfd86", str(error))
        self.assertNotIn("top-secret", str(error))
        self.assertNotIn("private upstream details", str(error))
        mock_open.assert_called_once()
        mock_sleep.assert_not_called()
        body_reader.read.assert_called_once_with(_ERROR_BODY_BYTES + 1)
        body_reader.close.assert_called_once()

    @patch("apps.cms.services.news.feed_parser.time.sleep")
    @patch("apps.cms.services.news.feed_parser.safe_urlopen")
    def test_503_retries_with_bounded_backoff_then_succeeds(self, mock_open, mock_sleep):
        context, _response = _successful_response(b"<rss>ok</rss>")
        mock_open.side_effect = [
            _http_error(503),
            _http_error(503),
            context,
        ]

        result = fetch_feed("https://news.ucmerced.edu/feed")

        self.assertEqual(result, b"<rss>ok</rss>")
        self.assertEqual(mock_open.call_count, 3)
        self.assertEqual(mock_sleep.call_args_list, [call(0.25), call(0.5)])

    @patch("apps.cms.services.news.feed_parser.time.sleep")
    @patch("apps.cms.services.news.feed_parser.safe_urlopen")
    def test_429_stops_after_max_attempts(self, mock_open, mock_sleep):
        mock_open.side_effect = [_http_error(429), _http_error(429), _http_error(429)]

        with self.assertRaises(FeedFetchError) as raised:
            fetch_feed("https://news.ucmerced.edu/feed")

        error = raised.exception
        self.assertEqual(error.status, 429)
        self.assertTrue(error.retryable)
        self.assertEqual(error.attempts, 3)
        self.assertEqual(mock_open.call_count, 3)
        self.assertEqual(mock_sleep.call_args_list, [call(0.25), call(0.5)])

    @patch("apps.cms.services.news.feed_parser.time.sleep")
    @patch("apps.cms.services.news.feed_parser.safe_urlopen")
    def test_non_retryable_404_is_attempted_once(self, mock_open, mock_sleep):
        mock_open.side_effect = _http_error(404, content_type="application/problem+json")

        with self.assertRaises(FeedFetchError) as raised:
            fetch_feed("https://news.ucmerced.edu/feed")

        self.assertEqual(raised.exception.status, 404)
        self.assertEqual(raised.exception.content_type, "application/problem+json")
        self.assertFalse(raised.exception.retryable)
        self.assertEqual(raised.exception.attempts, 1)
        mock_open.assert_called_once()
        mock_sleep.assert_not_called()


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
