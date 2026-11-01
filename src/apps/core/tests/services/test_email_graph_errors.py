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
from apps.core.services.email.graph.errors import (
    graph_error_code,
    identity_error_code,
    request_id,
    retry_after_seconds,
    send_mail_error,
    token_endpoint_error,
)
from apps.core.services.email.graph.transport import HttpResponse
from apps.core.tests.services.test_email_graph import REQUEST_ID, RESPONSE_TEXT

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


class GraphErrorCodeTests(SimpleTestCase):
    def test_returns_the_top_level_error_code(self):
        body = as_body({"error": {"code": "ErrorSendAsDenied", "message": RESPONSE_TEXT}})

        self.assertEqual(graph_error_code(body), "ErrorSendAsDenied")

    def test_falls_back_to_the_inner_error_code_in_either_spelling(self):
        for key in ("innerError", "innererror"):
            with self.subTest(key=key):
                body = as_body({"error": {"message": RESPONSE_TEXT, key: {"code": "InnerCode"}}})

                self.assertEqual(graph_error_code(body), "InnerCode")

    def test_the_top_level_code_wins_over_the_inner_code(self):
        body = as_body({"error": {"code": "OuterCode", "innerError": {"code": "InnerCode"}}})

        self.assertEqual(graph_error_code(body), "OuterCode")

    def test_an_unsafe_top_level_code_falls_back_to_a_safe_inner_code(self):
        body = as_body({"error": {"code": "not a safe code", "innerError": {"code": "InnerCode"}}})

        self.assertEqual(graph_error_code(body), "InnerCode")

    def test_accepts_the_shortest_and_longest_allowed_codes(self):
        for code in ("ab", "a" + "b" * 63, "Error_Code.With-Chars9"):
            with self.subTest(length=len(code)):
                self.assertEqual(graph_error_code(as_body({"error": {"code": code}})), code)

    def test_rejects_codes_outside_the_allow_list(self):
        values = [
            "bad code",
            "bad\ncode",
            "<b>bold</b>",
            "",
            "x",  # too short
            "1startswithdigit",
            "a" * 65,  # too long
            "caf\N{LATIN SMALL LETTER E WITH ACUTE}",
            RESPONSE_TEXT + " with spaces",
        ]
        for code in values:
            with self.subTest(code=code):
                self.assertEqual(graph_error_code(as_body({"error": {"code": code}})), "")

    def test_rejects_codes_that_are_not_strings(self):
        for code in (123, True, None, ["ErrorCode"], {"code": "ErrorCode"}):
            with self.subTest(code=code):
                self.assertEqual(graph_error_code(as_body({"error": {"code": code}})), "")

    def test_ignores_an_error_or_inner_error_that_is_not_an_object(self):
        payloads = [
            {"error": "invalid_client"},
            {"error": ["ErrorCode"]},
            {"error": {"innerError": "InnerCode"}},
            {"error": {"innerError": ["InnerCode"]}},
            {"error": {"innerError": None}},
            {"message": "no error key"},
        ]
        for payload in payloads:
            with self.subTest(payload=payload):
                self.assertEqual(graph_error_code(as_body(payload)), "")

    def test_unreadable_bodies_give_an_empty_code(self):
        for body in UNREADABLE_BODIES:
            with self.subTest(body=body):
                self.assertEqual(graph_error_code(body), "")


class IdentityErrorCodeTests(SimpleTestCase):
    def test_combines_the_oauth_error_with_the_first_aadsts_number(self):
        body = as_body({"error": "invalid_client", "error_codes": [7000215], "error_description": RESPONSE_TEXT})

        self.assertEqual(identity_error_code(body), "invalid_client AADSTS7000215")

    def test_only_the_first_error_number_is_used(self):
        body = as_body({"error": "invalid_grant", "error_codes": [50126, 50053]})

        self.assertEqual(identity_error_code(body), "invalid_grant AADSTS50126")

    def test_an_error_without_numbers_is_returned_alone(self):
        self.assertEqual(identity_error_code(as_body({"error": "invalid_scope"})), "invalid_scope")

    def test_numbers_without_a_usable_error_are_returned_without_a_leading_space(self):
        for payload in ({"error_codes": [7000215]}, {"error": "bad error!", "error_codes": [7000215]}):
            with self.subTest(payload=payload):
                self.assertEqual(identity_error_code(as_body(payload)), "AADSTS7000215")

    def test_accepts_the_largest_eight_digit_number(self):
        body = as_body({"error": "invalid_client", "error_codes": [99999999]})

        self.assertEqual(identity_error_code(body), "invalid_client AADSTS99999999")

    def test_ignores_numbers_that_are_not_plain_positive_integers(self):
        values = [[True], [False], [-5], [0], [10**8], [1.5], ["7000215"], [None], [[7000215]], [], "7000215", 7000215]
        for numbers in values:
            with self.subTest(error_codes=numbers):
                body = as_body({"error": "invalid_client", "error_codes": numbers})

                self.assertEqual(identity_error_code(body), "invalid_client")

    def test_unsafe_or_missing_errors_give_an_empty_code(self):
        for payload in ({"error": "bad error!"}, {"error": {"nested": True}}, {"error": None}, {}):
            with self.subTest(payload=payload):
                self.assertEqual(identity_error_code(as_body(payload)), "")

    def test_unreadable_bodies_give_an_empty_code(self):
        for body in UNREADABLE_BODIES:
            with self.subTest(body=body):
                self.assertEqual(identity_error_code(body), "")


class TokenEndpointErrorTests(SimpleTestCase):
    BODY = as_body(
        {
            "error": "invalid_client",
            "error_description": f"AADSTS7000215: Invalid client secret provided. {RESPONSE_TEXT}",
            "error_codes": [7000215],
            "trace_id": "trace-id-value",
            "correlation_id": "correlation-id-value",
        }
    )

    def assert_message_is_clean(self, error):
        for leaked in (RESPONSE_TEXT, "Invalid client secret", "trace-id-value", "correlation-id-value"):
            self.assertNotIn(leaked, str(error))

    def test_throttling_and_server_errors_are_transient_and_carry_retry_after(self):
        cases = [
            (408, {"retry-after": "5"}, 5.0),
            (429, {"retry-after": "30"}, 30.0),
            (429, {}, None),
            (500, {}, None),
            (502, {"retry-after": "7"}, 7.0),
            (503, {"retry-after": "99999"}, 3600.0),
            (599, {"retry-after": "not-a-number"}, None),
        ]
        for status, headers, retry_after in cases:
            with self.subTest(status=status, headers=headers):
                error = token_endpoint_error(HttpResponse(status, headers, self.BODY))

                self.assertIsInstance(error, TransientEmailDeliveryError)
                self.assertEqual(error.outcome, PROVIDER_OUTCOME_TRANSIENT)
                self.assertEqual(error.retry_after, retry_after)
                self.assertIn("temporarily unavailable", str(error))
                self.assert_message_is_clean(error)

    def test_credential_rejections_are_permanent_and_name_the_error_codes(self):
        for status in (400, 401, 403, 404):
            with self.subTest(status=status):
                error = token_endpoint_error(HttpResponse(status, {}, self.BODY))

                self.assertIsInstance(error, PermanentEmailDeliveryError)
                self.assertEqual(error.outcome, PROVIDER_OUTCOME_PERMANENT)
                self.assertIsNone(error.retry_after)
                self.assertEqual(str(error), "Microsoft rejected the Graph credentials (invalid_client AADSTS7000215).")
                self.assert_message_is_clean(error)

    def test_a_rejection_without_a_usable_code_names_nothing(self):
        for body in UNREADABLE_BODIES + [as_body({"error": "bad error!"})]:
            with self.subTest(body=body):
                error = token_endpoint_error(HttpResponse(400, {}, body))

                self.assertEqual(str(error), "Microsoft rejected the Graph credentials.")


class SendMailErrorTests(SimpleTestCase):
    BODY = as_body(
        {
            "error": {
                "code": "ErrorSendAsDenied",
                "message": f"Not allowed to send as this user. {RESPONSE_TEXT}",
                "innerError": {"request-id": "inner-request-id-value", "date": "2026-10-26T09:00:00"},
            }
        }
    )

    def error_for(self, status, headers=None, body=None):
        return send_mail_error(HttpResponse(status, headers or {}, self.BODY if body is None else body))

    def assert_message_is_clean(self, error):
        for leaked in (RESPONSE_TEXT, "Not allowed to send", "inner-request-id-value"):
            self.assertNotIn(leaked, str(error))

    def test_throttling_and_temporary_unavailability_are_transient_and_carry_retry_after(self):
        cases = [
            (408, {"retry-after": "5"}, 5.0),
            (429, {"retry-after": "30"}, 30.0),
            (429, {}, None),
            (503, {"retry-after": "120"}, 120.0),
            (503, {"retry-after": "99999"}, 3600.0),
            (503, {"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}, None),
        ]
        for status, headers, retry_after in cases:
            with self.subTest(status=status, headers=headers):
                error = self.error_for(status, headers)

                self.assertIsInstance(error, TransientEmailDeliveryError)
                self.assertEqual(error.outcome, PROVIDER_OUTCOME_TRANSIENT)
                self.assertEqual(error.retry_after, retry_after)
                self.assertIn("temporarily rejected", str(error))
                self.assert_message_is_clean(error)

    def test_an_unauthorized_response_is_transient_because_the_token_will_be_refreshed(self):
        error = self.error_for(401)

        self.assertIsInstance(error, TransientEmailDeliveryError)
        self.assertIn("will be refreshed", str(error))
        self.assertIsNone(error.retry_after)
        self.assert_message_is_clean(error)

    def test_a_full_mailbox_is_permanent_with_a_specific_message(self):
        for body in (self.BODY, b""):
            with self.subTest(body=body):
                error = self.error_for(507, body=body)

                self.assertIsInstance(error, PermanentEmailDeliveryError)
                self.assertIn("mailbox is full", str(error))
                self.assert_message_is_clean(error)

    def test_client_errors_are_permanent_and_name_the_allow_listed_code(self):
        for status in (400, 403, 404, 413, 422):
            with self.subTest(status=status):
                error = self.error_for(status)

                self.assertIsInstance(error, PermanentEmailDeliveryError)
                self.assertEqual(error.outcome, PROVIDER_OUTCOME_PERMANENT)
                self.assertEqual(str(error), "Microsoft Graph rejected the request (ErrorSendAsDenied).")
                self.assert_message_is_clean(error)

    def test_client_errors_without_a_usable_code_name_nothing(self):
        for body in UNREADABLE_BODIES:
            with self.subTest(body=body):
                error = self.error_for(400, body=body)

                self.assertEqual(str(error), "Microsoft Graph rejected the request.")

    def test_server_errors_and_unexpected_statuses_are_uncertain(self):
        for status in (500, 502, 504, 599, 200, 204, 302):
            with self.subTest(status=status):
                error = self.error_for(status)

                self.assertIsInstance(error, UncertainEmailDeliveryError)
                self.assertEqual(error.outcome, PROVIDER_OUTCOME_UNCERTAIN)
                self.assertIsNone(error.retry_after)
                self.assertEqual(
                    str(error),
                    f"Microsoft Graph returned HTTP {status}; delivery could not be confirmed (ErrorSendAsDenied).",
                )
                self.assert_message_is_clean(error)

    def test_uncertain_errors_without_a_usable_code_name_nothing_after_the_status(self):
        error = self.error_for(502, body=b"<html>Bad Gateway</html>")

        self.assertEqual(str(error), "Microsoft Graph returned HTTP 502; delivery could not be confirmed.")


class HostileBodyTests(SimpleTestCase):
    NESTED = b"[" * 70_000

    def test_deeply_nested_bodies_are_treated_as_unreadable(self):
        self.assertEqual(graph_error_code(self.NESTED), "")
        self.assertEqual(identity_error_code(self.NESTED), "")

    def test_classification_survives_deeply_nested_bodies(self):
        for build in (send_mail_error, token_endpoint_error):
            with self.subTest(build.__name__):
                self.assertIsInstance(build(HttpResponse(400, {}, self.NESTED)), PermanentEmailDeliveryError)
