"""``GraphTraceReader``: the exact trace query, the next-page rebuild, the size cap, Microsoft's refusals, and no
delivery-rate lane touched. Microsoft is faked behind the real transport, so every request passes its allow-list."""

from datetime import UTC, datetime, timedelta

from django.test import SimpleTestCase, TestCase

from apps.core.models import DeliveryRateState, DeliveryUsageBucket
from apps.core.services.email.graph import transport
from apps.core.services.email.graph.tracing import limits, reader
from apps.core.services.email.graph.tracing.reader import (
    GraphTraceBusy,
    GraphTraceError,
    GraphTraceNotPermitted,
    GraphTraceReader,
)

from . import NEXT, PRIVATE, SENDER, TRACES, TraceSetupMixin, trace_page, trace_row

START = datetime(2026, 11, 17, 8, 0, 5, tzinfo=UTC)
END = START + timedelta(hours=24)
LOGGER = "apps.core.services.email.graph.tracing.reader"
WINDOW = (
    "%20and%20receivedDateTime%20ge%202026-11-17T08%3A00%3A05Z%20and%20receivedDateTime%20le%202026-11-18T08%3A00%3A05Z"
)


class NextLinkTests(SimpleTestCase):
    def test_only_the_skip_token_is_kept_and_re_quoted(self):
        cases = {
            "plain": "plain",
            "ab~c": "ab%7Ec",
            "a+b": "a%2Bb",  # a literal "+" is not a space
            "a%2Fb%3D%3D": "a%2Fb%3D%3D",
            "x%27%20or%201": "x%27%20or%201",
        }
        for raw, expected in cases.items():
            with self.subTest(raw):
                self.assertEqual(reader.next_skiptoken(f"{NEXT}{raw}"), expected)
        self.assertEqual(reader.next_skiptoken(None), "")

    def test_a_link_anywhere_else_is_refused(self):
        hostile = (
            f"http://graph.microsoft.com{TRACES}?$skiptoken=a",
            f"https://graph.microsoft.com.evil.example{TRACES}?$skiptoken=a",
            f"https://evil.example@graph.microsoft.com{TRACES}?$skiptoken=a",
            f"https://graph.microsoft.com:8443{TRACES}?$skiptoken=a",
            "https://graph.microsoft.com/v1.0/users/i2g@ucmerced.edu/messages?$skiptoken=a",
            "https://graph.microsoft.com/beta/admin/exchange/tracing/messageTraces?$skiptoken=a",
            f"https://graph.microsoft.com{TRACES}/../users?$skiptoken=a",
            f"https://graph.microsoft.com{TRACES}?$skiptoken=a#x",
            f"https://graph.microsoft.com{TRACES}?$top=10",
            f"https://graph.microsoft.com{TRACES}?$skiptoken=",
            f"https://graph.microsoft.com{TRACES}?$skiptoken=a&$skiptoken=b",
            f"https://graph.microsoft.com{TRACES}?$skiptoken={'a' * 2049}",
            "//graph.microsoft.com/x",
            12,
        )
        for link in hostile:
            with self.subTest(link=str(link)[:80]), self.assertRaises(GraphTraceError):
                reader.next_skiptoken(link)


class ReaderTests(TraceSetupMixin, TestCase):
    def reader(self, sender=SENDER):
        return GraphTraceReader(self.config, sender)

    def test_the_query_is_fully_encoded_and_allowed(self):
        self.reader("first.last+tag@ucmerced.edu").page(START, END)

        request = self.microsoft.traces[0]
        self.assertEqual(request["method"], "GET")
        self.assertEqual(
            request["path"],
            f"{TRACES}?$filter=senderAddress%20eq%20%27first.last%2Btag%40ucmerced.edu%27{WINDOW}&$top=1000",
        )
        self.assertEqual(request["max_bytes"], limits.max_bytes())
        self.assertTrue(transport.is_allowed("GET", transport.GRAPH_HOST, request["path"]))

    def test_the_next_page_is_rebuilt_from_the_skip_token_only(self):
        self.microsoft.pages = [trace_page([trace_row()], skiptoken="n~1+2"), trace_page([trace_row()])]
        traces = self.reader()

        first = traces.page(START, END, top=5)
        second = traces.page(START, END, top=5, skiptoken=first.skiptoken)

        self.assertEqual((len(first.rows), first.skiptoken, second.skiptoken), (1, "n%7E1%2B2", ""))
        path = self.microsoft.traces[1]["path"]
        self.assertTrue(path.endswith("&$top=5&$skiptoken=n%7E1%2B2"))
        self.assertIn("senderAddress%20eq%20%27i2g%40ucmerced.edu%27", path)
        self.assertNotIn("whatever", path)
        self.assertTrue(transport.is_allowed("GET", transport.GRAPH_HOST, path))

    def test_page_size_is_bounded_and_a_window_longer_than_a_day_is_refused(self):
        self.reader().page(START, END, top=10**6)
        self.assertTrue(self.microsoft.traces[0]["path"].endswith(f"&$top={limits.page_size()}"))
        with self.assertRaises(ValueError):
            self.reader().page(START, END + timedelta(seconds=1))
        with self.assertRaises(ValueError):
            self.reader().page(END, START)

    def test_a_truncated_or_unreadable_response_is_an_error(self):
        for page in (
            trace_page([trace_row()], truncated=True),
            trace_page(body=b"not json"),
            trace_page(body=b'{"value": {}}'),
            trace_page(body=b"[]"),
        ):
            self.microsoft.pages = [page]
            with self.subTest(body=page.body[:20]), self.assertRaises(GraphTraceError):
                self.reader().page(START, END)

    def test_non_object_rows_are_dropped(self):
        self.microsoft.pages = [trace_page([trace_row(), "x", 3, None])]
        self.assertEqual(len(self.reader().page(START, END).rows), 1)

    def test_microsofts_refusals_are_mapped(self):
        self.enterContext(self.assertLogs(LOGGER, level="WARNING"))
        cases = (
            (429, {"retry-after": "120"}, GraphTraceBusy),
            (503, {}, GraphTraceBusy),
            (401, {}, GraphTraceNotPermitted),
            (403, {}, GraphTraceNotPermitted),
            (500, {}, GraphTraceError),
            (400, {}, GraphTraceError),
        )
        for status, headers, error in cases:
            self.microsoft.pages = [trace_page(status=status, headers=headers)]
            with self.subTest(status), self.assertRaises(error) as caught:
                self.reader().page(START, END)
            self.assertIs(type(caught.exception), error)
        self.microsoft.pages = [trace_page(status=429, headers={"retry-after": "120"})]
        with self.assertRaises(GraphTraceBusy) as caught:
            self.reader().page(START, END)
        self.assertEqual(caught.exception.retry_after, 120.0)

    def test_a_refusal_forgets_the_token_once(self):
        traces = self.reader()
        traces.page(START, END)
        traces.page(START, END)
        self.assertEqual(self.microsoft.tokens, 1)  # cached

        self.microsoft.pages = [trace_page(status=403), trace_page()]
        with self.assertLogs(LOGGER, level="WARNING"), self.assertRaises(GraphTraceNotPermitted):
            traces.page(START, END)
        traces.page(START, END)

        self.assertEqual(self.microsoft.tokens, 2)

    def test_no_delivery_rate_lane_is_used_and_nothing_private_is_logged(self):
        self.microsoft.pages = [trace_page(status=429, body=b'{"error": {"code": "TooManyRequests"}}')]
        with self.assertLogs(LOGGER, level="WARNING") as logs:
            with self.assertRaises(GraphTraceBusy):
                self.reader().page(START, END)

        self.assertEqual((DeliveryRateState.objects.count(), DeliveryUsageBucket.objects.count()), (0, 0))
        self.assertIn("status=429 code=TooManyRequests", logs.output[0])
        for value in PRIVATE:
            self.assertNotIn(value, "\n".join(logs.output))
