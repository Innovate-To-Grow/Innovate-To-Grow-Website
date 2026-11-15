"""Parsing and classification helpers that turn Microsoft responses into delivery errors (``graph.errors``).

Every message they produce is generic plus, at most, an allow-listed error code: nothing from a response body or
header other than a validated code may reach an exception, because those messages are stored and shown to staff.
"""

import json

from django.conf import settings
from django.test import SimpleTestCase

from apps.core.services.aws.provider_outcomes import (
    PROVIDER_OUTCOME_PERMANENT,
    PROVIDER_OUTCOME_TRANSIENT,
    PROVIDER_OUTCOME_UNCERTAIN,
)
from apps.core.services.email import (
    PermanentEmailDeliveryError,
    TransientEmailDeliveryError,
    UncertainEmailDeliveryError,
)
from apps.core.services.email.graph.transport.errors import request_id, retry_after_seconds
from apps.core.tests.services.graph.provider.test_email_graph import REQUEST_ID

OUTCOME_OF = {
    TransientEmailDeliveryError: PROVIDER_OUTCOME_TRANSIENT,
    PermanentEmailDeliveryError: PROVIDER_OUTCOME_PERMANENT,
    UncertainEmailDeliveryError: PROVIDER_OUTCOME_UNCERTAIN,
}
UNREADABLE_BODIES = [b"", b"not json", b'{"error": {', b"[]", b'"text"', b"null", b"123", b"\xff\xfe\x00", b"\x80abc"]


def as_body(payload):
    return json.dumps(payload).encode()


class RetryAfterSecondsTests(SimpleTestCase):
    def test_plain_integer_seconds_become_floats(self):
        for raw, expected in (("0", 0.0), ("30", 30.0), (" 7 ", 7.0), ("3600", 3600.0)):
            with self.subTest(raw=raw):
                result = retry_after_seconds({"retry-after": raw})

                self.assertEqual(result, expected)
                self.assertIsInstance(result, float)

    def test_long_delays_are_capped_at_one_hour(self):
        self.assertEqual(settings.GRAPH_MAX_RETRY_AFTER_SECONDS, 3600)
        for raw in ("3601", "99999", "999999"):
            with self.subTest(raw=raw):
                self.assertEqual(retry_after_seconds({"retry-after": raw}), 3600.0)

    def test_long_numbers_are_capped_instead_of_ignored(self):
        for raw in ("1000000", "999999999"):
            with self.subTest(raw=raw):
                self.assertEqual(
                    retry_after_seconds({"retry-after": raw}), float(settings.GRAPH_MAX_RETRY_AFTER_SECONDS)
                )
        with self.settings(GRAPH_MAX_RETRY_AFTER_SECONDS=60):
            self.assertEqual(retry_after_seconds({"retry-after": "61"}), 60.0)

    def test_numbers_beyond_nine_digits_are_ignored(self):
        self.assertIsNone(retry_after_seconds({"retry-after": "1" * 10}))

    def test_anything_that_is_not_a_plain_ascii_number_means_no_hint(self):
        values = [
            "",
            "   ",
            "abc",
            "-1",
            "+5",
            "1.5",
            "1e3",
            "1_000",
            "5 seconds",
            "Wed, 21 Oct 2026 07:28:00 GMT",
            "\N{SUPERSCRIPT TWO}",  # a digit by str.isdigit() but not a number
            "\N{ARABIC-INDIC DIGIT THREE}\N{ARABIC-INDIC DIGIT ZERO}",  # int() would happily read this as 30
            "\N{FULLWIDTH DIGIT THREE}\N{FULLWIDTH DIGIT ZERO}",  # ... and this as 30 as well
        ]
        for raw in values:
            with self.subTest(raw=raw):
                self.assertIsNone(retry_after_seconds({"retry-after": raw}))

    def test_a_missing_header_means_no_hint(self):
        self.assertIsNone(retry_after_seconds({}))
        self.assertIsNone(retry_after_seconds({"x-other": "30"}))


class RequestIdTests(SimpleTestCase):
    def test_returns_the_request_id_header(self):
        self.assertEqual(request_id({"request-id": REQUEST_ID}), REQUEST_ID)

    def test_falls_back_to_the_client_request_id_header(self):
        self.assertEqual(request_id({"client-request-id": REQUEST_ID}), REQUEST_ID)
        self.assertEqual(request_id({"request-id": "", "client-request-id": REQUEST_ID}), REQUEST_ID)

    def test_prefers_the_request_id_over_the_client_request_id(self):
        headers = {"request-id": REQUEST_ID, "client-request-id": "ffffffff-ffff-ffff-ffff-ffffffffffff"}

        self.assertEqual(request_id(headers), REQUEST_ID)

    def test_accepts_the_shortest_and_longest_allowed_ids(self):
        for value in ("abcdefgh", "a" * 64):
            with self.subTest(length=len(value)):
                self.assertEqual(request_id({"request-id": value}), value)

    def test_rejects_values_that_could_forge_or_pollute_a_log_line(self):
        values = [
            "abcdefg",  # one character too short
            "a" * 65,  # one character too long
            "has space 12345",
            "line\nbreak12345",
            "trailing-newline\n",
            "semi;colon12345",
            "unicod\N{LATIN SMALL LETTER E WITH ACUTE}-id-12345",
            "%s%s%s%s%s%s%s%s",
            "<script>alert(1)</script>",
        ]
        for value in values:
            with self.subTest(value=value):
                self.assertEqual(request_id({"request-id": value}), "")

    def test_absent_headers_give_an_empty_string(self):
        self.assertEqual(request_id({}), "")
        self.assertEqual(request_id({"request-id": ""}), "")
